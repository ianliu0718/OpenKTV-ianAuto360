import sys
import os
import glob
import queue
import re

# ==========================================
# 【終極修復】修正 Bad file descriptor 崩潰問題
# ==========================================
system_log_queue = queue.Queue()

class GUIWriter:
    def __init__(self):
        # 【關鍵】開啟系統底層的空裝置 (devnull)，取得真實合法的檔案描述符
        self.null_file = open(os.devnull, 'w')

    def write(self, data):
        # 攔截所有 print 和系統報錯，丟進佇列中
        if data and data.strip():
            system_log_queue.put(data.strip())

    def flush(self):
        pass

    def isatty(self):
        return False

    def fileno(self):
        # 【關鍵】回傳真實合法的空裝置描述符，徹底騙過 Flask 的 click 模組！
        return self.null_file.fileno()

if getattr(sys, 'frozen', False):
    # 打包成 EXE 後，強制把所有輸出導向我們的攔截器
    sys_writer = GUIWriter()
    sys.stdout = sys_writer
    sys.stderr = sys_writer

# ==========================================
# 正常 Import 區
# ==========================================
import tkinter as tk
from tkinter import messagebox
# ... 下面的 import 保留原樣 ...
import subprocess
import shutil
import threading
import socket
import json
import time
import webbrowser
import ipaddress
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, request, send_from_directory
from flask_socketio import SocketIO, emit
import multiprocessing

# ==========================================
# 設定區
# ==========================================
APP_VERSION = "v1.0.3"

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable) 
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
FFMPEG_DIR = os.path.join(BASE_DIR, "ffmpeg", "bin")
YT_DLP_PATH = os.path.join(BASE_DIR, "yt-dlp.exe")

def get_ytdlp_command():
    if os.path.exists(YT_DLP_PATH):
        return [YT_DLP_PATH]
    if not getattr(sys, 'frozen', False) and shutil.which("py"):
        return ["py", "-3.10", "-m", "yt_dlp"]
    return [sys.executable, "-m", "yt_dlp"]

def get_ffmpeg_location():
    if os.path.isdir(FFMPEG_DIR):
        return FFMPEG_DIR
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        return os.path.dirname(ffmpeg_path)
    winget_ffmpeg = glob.glob(os.path.expandvars(
        r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_*\**\ffmpeg.exe"
    ), recursive=True)
    return os.path.dirname(winget_ffmpeg[0]) if winget_ffmpeg else None

def get_ffprobe_path(ffmpeg_path):
    """Return the FFprobe executable beside FFmpeg or from PATH."""
    sibling_path = os.path.join(os.path.dirname(ffmpeg_path), 'ffprobe.exe')
    return sibling_path if os.path.exists(sibling_path) else shutil.which('ffprobe')

def get_audio_channel_count(filename):
    """Return the first audio stream channel count for a song, or zero when unavailable."""
    song_path = os.path.join(SONGS_DIR, os.path.basename(filename))
    ffmpeg_path = os.path.join(FFMPEG_DIR, 'ffmpeg.exe') if os.path.isdir(FFMPEG_DIR) else shutil.which('ffmpeg')
    ffprobe_path = get_ffprobe_path(ffmpeg_path) if ffmpeg_path else None
    if not ffprobe_path or not os.path.exists(song_path):
        return 0
    result = subprocess.run(
        [ffprobe_path, '-v', 'error', '-select_streams', 'a:0',
         '-show_entries', 'stream=channels', '-of', 'default=noprint_wrappers=1:nokey=1', song_path],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
    )
    try:
        return int(result.stdout.strip())
    except (TypeError, ValueError):
        return 0

ffmpeg_location = get_ffmpeg_location()
if ffmpeg_location:
    os.environ["PATH"] += os.pathsep + ffmpeg_location
os.environ["PATH"] += os.pathsep + BASE_DIR

SONGS_DIR = os.path.join(BASE_DIR, "ktv_songs")
TEMP_BASE_DIR = os.path.join(BASE_DIR, "temp_processing") 
SUBTITLE_EXTENSIONS = {"srt", "lrc", "vtt"}

if not os.path.exists(SONGS_DIR): os.makedirs(SONGS_DIR)
if not os.path.exists(TEMP_BASE_DIR): os.makedirs(TEMP_BASE_DIR)

# ==========================================
# Flask + SocketIO 伺服器
# ==========================================
app = Flask(__name__, template_folder=TEMPLATES_DIR)
app.config['SECRET_KEY'] = 'ktv_secret'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

LOCAL_IP = get_local_ip()
PORT = 5000
TLS_CERT_PATH = os.path.join(BASE_DIR, "ktv-local.crt")
TLS_KEY_PATH = os.path.join(BASE_DIR, "ktv-local.key")

def ensure_tls_certificate():
    """Create a reusable self-signed certificate for localhost and the LAN IP."""
    if os.path.exists(TLS_CERT_PATH) and os.path.exists(TLS_KEY_PATH):
        return TLS_CERT_PATH, TLS_KEY_PATH

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "ianAutoKTV Local"),
        x509.NameAttribute(NameOID.COMMON_NAME, LOCAL_IP),
    ])
    san_names = [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
    try:
        san_names.append(x509.IPAddress(ipaddress.ip_address(LOCAL_IP)))
    except ValueError:
        san_names.append(x509.DNSName(LOCAL_IP))
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(minutes=1))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=825))
        .add_extension(x509.SubjectAlternativeName(san_names), critical=False)
        .sign(private_key, hashes.SHA256())
    )
    with open(TLS_KEY_PATH, "wb") as key_file:
        key_file.write(private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        ))
    with open(TLS_CERT_PATH, "wb") as cert_file:
        cert_file.write(certificate.public_bytes(serialization.Encoding.PEM))
    return TLS_CERT_PATH, TLS_KEY_PATH

def broadcast_log(msg):
    # 用 print 就會自動被我們的 GUIWriter 抓走並顯示在介面上
    print(msg)
    socketio.emit('admin_log', {'msg': msg})

# ------------------------------------------
# Flask 路由
# ------------------------------------------
@app.route('/player')
def page_player(): return render_template('player.html')

@app.route('/remote')
def page_remote(): return render_template('remote.html')

@app.route('/admin')
def page_admin(): return render_template('admin.html')

@app.route('/combo')  
def page_combo(): return render_template('combo.html')

@app.route('/soundtouch-prototype')
def page_soundtouch_prototype():
    """Serve the isolated SoundTouch KEY validation page."""
    return send_from_directory(BASE_DIR, 'soundtouch-prototype.html')

@app.route('/')
def page_index(): return render_template('remote.html')

@app.route('/songs/<path:filename>')
def serve_song(filename):
    return send_from_directory(SONGS_DIR, filename)

def _play_video_payload(filename):
    """Build a playback event payload with server-confirmed audio metadata."""
    return {
        'filename': filename,
        'title': filename,
        'audio_channels': get_audio_channel_count(filename),
    }

@app.route('/subtitles/<path:filename>')
def serve_subtitle(filename):
    """Serve a stored WebVTT subtitle file for a song."""
    return send_from_directory(SONGS_DIR, filename, mimetype='text/vtt; charset=utf-8')

@app.route('/api/list')
def get_song_list():
    songs = [f for f in os.listdir(SONGS_DIR) if f.lower().endswith('.mp4')]
    return json.dumps(songs) 

@app.route('/api/subtitles')
def get_subtitle_list():
    """Return MP4 filenames that have a matching WebVTT subtitle file."""
    subtitles = {
        os.path.splitext(filename)[0] + '.mp4'
        for filename in os.listdir(SONGS_DIR)
        if filename.lower().endswith('.vtt')
    }
    return json.dumps(sorted(subtitles), ensure_ascii=False)

@app.route('/api/subtitles/upload', methods=['POST'])
def upload_subtitle():
    """Convert subtitle file or text and save it beside its matching song."""
    song_filename = os.path.basename(request.form.get('song', ''))
    subtitle_file = request.files.get('subtitle')
    if not song_filename.lower().endswith('.mp4') or not os.path.exists(os.path.join(SONGS_DIR, song_filename)):
        return json.dumps({'success': False, 'error': '請選擇有效的歌曲'}), 400
    subtitle_text = request.form.get('subtitle_content', '').strip()
    if subtitle_file and subtitle_file.filename and subtitle_text:
        return json.dumps({'success': False, 'error': '字幕檔案與文字內容請擇一輸入'}), 400
    if subtitle_file and subtitle_file.filename:
        subtitle_extension = os.path.splitext(subtitle_file.filename)[1].lower().lstrip('.')
        if subtitle_extension not in SUBTITLE_EXTENSIONS:
            return json.dumps({'success': False, 'error': '只支援 .srt、.lrc 或 .vtt 字幕檔'}), 400
    elif subtitle_text:
        subtitle_extension = str(request.form.get('subtitle_extension', '')).lower().lstrip('.')
    else:
        return json.dumps({'success': False, 'error': '請選擇字幕檔或輸入字幕文字'}), 400
    try:
        content = subtitle_file.read().decode('utf-8-sig') if subtitle_file else subtitle_text
        subtitle_extension = detect_subtitle_format(content, subtitle_extension)
        output_name = save_subtitle(song_filename, content, subtitle_extension)
        socketio.emit('refresh_list')
        return json.dumps({'success': True, 'filename': output_name}, ensure_ascii=False)
    except (UnicodeDecodeError, OSError, ValueError) as error:
        return json.dumps({'success': False, 'error': f'字幕檔處理失敗：{error}'}), 400

@app.route('/api/videos/optimize', methods=['POST'])
def optimize_video():
    """Convert an uploaded MP4 to H.264 up to 1080p and replace its song file."""
    video_file = request.files.get('video')
    if not video_file or not video_file.filename:
        broadcast_log('❌ 影片最佳化失敗：未選擇 MP4 檔案。')
        return json.dumps({'error': '請選擇要轉檔的 MP4 影片'}), 400
    filename = os.path.basename(video_file.filename)
    if not filename.lower().endswith('.mp4'):
        broadcast_log(f'❌ 影片最佳化失敗：檔案不是 MP4（{filename}）。')
        return json.dumps({'error': '影片檔必須是 .mp4'}), 400

    job_dir = os.path.join(TEMP_BASE_DIR, f'video_optimize_{time.time_ns()}')
    source_path = os.path.join(job_dir, filename)
    output_path = os.path.join(job_dir, f'{os.path.splitext(filename)[0]}.optimized.mp4')
    final_path = os.path.join(SONGS_DIR, filename)
    os.makedirs(job_dir, exist_ok=True)
    try:
        broadcast_log(f'=== 開始影片效能最佳化：{filename} ===')
        video_file.save(source_path)
        broadcast_log(f'📥 已接收影片：{filename}（{os.path.getsize(source_path):,} bytes）')
        ffmpeg_dir = get_ffmpeg_location()
        ffmpeg_path = os.path.join(ffmpeg_dir, 'ffmpeg.exe') if ffmpeg_dir else shutil.which('ffmpeg')
        if not ffmpeg_path:
            broadcast_log('❌ 影片最佳化失敗：找不到 FFmpeg。')
            return json.dumps({'error': '找不到 FFmpeg'}), 500
        broadcast_log(f'🔧 使用 FFmpeg：{ffmpeg_path}')
        broadcast_log('⏳ 正在重新編碼為 H.264 / 最高 1080p，請稍候...')
        command = [
            ffmpeg_path, '-y', '-i', source_path,
            '-map', '0:v:0', '-map', '0:a?',
            '-vf', "scale=w='min(1920,iw)':h=-2:force_original_aspect_ratio=decrease",
            '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23',
            '-pix_fmt', 'yuv420p', '-c:a', 'copy', '-movflags', '+faststart',
            output_path,
        ]
        result = subprocess.run(
            command, capture_output=True, text=True, encoding='utf-8', errors='replace',
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
        )
        if result.returncode != 0 or not os.path.exists(output_path):
            detail = result.stderr.strip()[-500:] if result.stderr else 'FFmpeg 未產生輸出檔案'
            broadcast_log(f'❌ FFmpeg 轉檔失敗（return code {result.returncode}）：{detail}')
            return json.dumps({'success': False, 'error': f'影片轉檔失敗：{detail}'}, ensure_ascii=False), 400
        if os.path.getsize(output_path) == 0:
            broadcast_log('❌ FFmpeg 轉檔失敗：輸出檔案為空。')
            return json.dumps({'success': False, 'error': '影片轉檔失敗：輸出檔案為空'}), 400
        broadcast_log(f'✅ FFmpeg 轉檔完成：輸出 {os.path.getsize(output_path):,} bytes。')
        shutil.move(output_path, final_path)
        broadcast_log(f'✅ 已取代原始影片：{filename}')
        socketio.emit('refresh_list')
        broadcast_log(f'=== 影片效能最佳化成功：{filename} ===')
        return json.dumps({'success': True, 'filename': filename}, ensure_ascii=False)
    except (OSError, ValueError) as error:
        broadcast_log(f'❌ 影片最佳化發生例外：{error}')
        return json.dumps({'success': False, 'error': f'影片轉檔失敗：{error}'}, ensure_ascii=False), 400
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)

def _create_six_channel_mp4(ffmpeg_path, ffprobe_path, source_path, vocal_path, accompaniment_path, output_path, normalize_volume=True):
    """Create one MP4 with original, guide, and instrumental stereo pairs."""
    loudnorm = 'loudnorm=I=-16:TP=-1.5:LRA=11,' if normalize_volume else ''
    audio_filter = (
        '[0:a]pan=mono|c0=0.5*FL+0.5*FR,aformat=sample_fmts=fltp:sample_rates=44100[original_l];'
        '[0:a]pan=mono|c0=0.5*FL+0.5*FR,aformat=sample_fmts=fltp:sample_rates=44100[original_r];'
        '[1:a]pan=stereo|c0=0.5*FL+0.5*FR|c1=0.5*FL+0.5*FR,volume=0.25,'
        'aformat=sample_fmts=fltp:sample_rates=44100[vocals];'
        f'[2:a]pan=stereo|c0=0.5*FL+0.5*FR|c1=0.5*FL+0.5*FR,{loudnorm}aresample=async=1,'
        'aformat=sample_fmts=fltp:sample_rates=44100[accompaniment];'
        '[vocals][accompaniment]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0,'
        f'{loudnorm}aresample=async=1,aformat=sample_fmts=fltp:sample_rates=44100[guide];'
        '[guide]pan=mono|c0=FL,aformat=sample_fmts=fltp:sample_rates=44100[guide_l];'
        '[guide]pan=mono|c0=FR,aformat=sample_fmts=fltp:sample_rates=44100[guide_r];'
        '[2:a]pan=mono|c0=0.5*FL+0.5*FR,aformat=sample_fmts=fltp:sample_rates=44100[accompaniment_l];'
        '[2:a]pan=mono|c0=0.5*FL+0.5*FR,aformat=sample_fmts=fltp:sample_rates=44100[accompaniment_r];'
        '[original_l][original_r][guide_l][guide_r][accompaniment_l][accompaniment_r]amerge=inputs=6,'
        'aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=5.1[audio]'
    )
    command = [
        ffmpeg_path, '-y', '-i', source_path, '-i', vocal_path, '-i', accompaniment_path,
        '-filter_complex', audio_filter,
        '-map', '0:v:0', '-map', '[audio]',
        '-c:v', 'copy', '-c:a', 'aac', '-b:a', '384k', '-movflags', '+faststart',
        '-metadata:s:a:0', 'title=原聲、導唱、伴奏（六聲道）', output_path,
    ]
    subprocess.run(
        command, check=True, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
    )
    probe_command = [
        ffprobe_path, '-v', 'error', '-select_streams', 'a:0',
        '-show_entries', 'stream=channels', '-of', 'default=noprint_wrappers=1:nokey=1', output_path,
    ]
    probe_result = subprocess.run(
        probe_command, check=True, capture_output=True, text=True,
        encoding='utf-8', errors='replace',
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
    )
    if probe_result.stdout.strip() != '6':
        raise RuntimeError(f'FFprobe 驗證失敗：輸出音訊聲道數為 {probe_result.stdout.strip() or "未知"}，預期 6')

@app.route('/api/videos/ai-vocal-remove', methods=['POST'])
def ai_vocal_remove_video():
    """Separate an uploaded MP4 into one six-channel KTV audio stream."""
    global is_processing
    if is_processing:
        return json.dumps({'error': '目前已有其他製作或轉檔工作進行中，請稍候'}), 409
    video_file = request.files.get('video')
    if not video_file or not video_file.filename:
        return json.dumps({'error': '請選擇要處理的 MP4 影片'}), 400
    filename = os.path.basename(video_file.filename)
    if not filename.lower().endswith('.mp4'):
        return json.dumps({'error': '影片檔必須是 .mp4'}), 400

    job_dir = os.path.join(TEMP_BASE_DIR, f'ai_vocal_remove_{time.time_ns()}')
    source_path = os.path.join(job_dir, 'input.mp4')
    output_path = os.path.join(job_dir, 'output.mp4')
    final_path = os.path.join(SONGS_DIR, filename)
    os.makedirs(job_dir, exist_ok=True)
    is_processing = True
    socketio.emit('task_status', {'status': 'busy'})
    try:
        video_file.save(source_path)
        broadcast_log(f'=== 開始 AI 去人聲：{filename} ===')
        p = multiprocessing.Process(target=_run_spleeter_process, args=(source_path, job_dir))
        p.start()
        p.join()
        if p.exitcode != 0:
            raise RuntimeError('Spleeter 分離失敗')
        vocal_path = os.path.join(job_dir, 'input', 'vocals.wav')
        accompaniment_path = os.path.join(job_dir, 'input', 'accompaniment.wav')
        if not os.path.exists(vocal_path) or not os.path.exists(accompaniment_path):
            raise RuntimeError('找不到 Spleeter 產生的音軌檔')
        ffmpeg_dir = get_ffmpeg_location()
        ffmpeg_path = os.path.join(ffmpeg_dir, 'ffmpeg.exe') if ffmpeg_dir else shutil.which('ffmpeg')
        if not ffmpeg_path:
            raise RuntimeError('找不到 FFmpeg')
        ffprobe_path = get_ffprobe_path(ffmpeg_path)
        if not ffprobe_path:
            raise RuntimeError('找不到 FFprobe，無法驗證六聲道輸出')
        _create_six_channel_mp4(
            ffmpeg_path, ffprobe_path, source_path, vocal_path, accompaniment_path,
            output_path, normalize_volume=False,
        )
        shutil.move(output_path, final_path)
        broadcast_log(f'✅ AI 去人聲完成：{filename}（六聲道：原聲 / 導唱 / 伴奏）')
        socketio.emit('refresh_list')
        return json.dumps({'success': True, 'filename': filename}, ensure_ascii=False)
    except (OSError, RuntimeError) as error:
        broadcast_log(f'❌ AI 去人聲失敗：{error}')
        return json.dumps({'error': str(error)}, ensure_ascii=False), 400
    finally:
        is_processing = False
        socketio.emit('task_status', {'status': 'idle'})
        shutil.rmtree(job_dir, ignore_errors=True)

@app.route('/api/videos/normalize-audio', methods=['POST'])
def normalize_video_audio():
    """Normalize an uploaded MP4 audio track to the shared KTV loudness target."""
    global is_processing
    if is_processing:
        return json.dumps({'error': '目前已有其他製作或轉檔工作進行中，請稍候'}), 409
    video_file = request.files.get('video')
    if not video_file or not video_file.filename:
        return json.dumps({'error': '請選擇要處理的 MP4 影片'}), 400
    filename = os.path.basename(video_file.filename)
    if not filename.lower().endswith('.mp4'):
        return json.dumps({'error': '影片檔必須是 .mp4'}), 400

    job_dir = os.path.join(TEMP_BASE_DIR, f'normalize_audio_{time.time_ns()}')
    source_path = os.path.join(job_dir, 'input.mp4')
    output_path = os.path.join(job_dir, 'output.mp4')
    final_path = os.path.join(SONGS_DIR, filename)
    os.makedirs(job_dir, exist_ok=True)
    is_processing = True
    socketio.emit('task_status', {'status': 'busy'})
    try:
        video_file.save(source_path)
        broadcast_log(f'=== 開始平衡音量：{filename} ===')
        ffmpeg_dir = get_ffmpeg_location()
        ffmpeg_path = os.path.join(ffmpeg_dir, 'ffmpeg.exe') if ffmpeg_dir else shutil.which('ffmpeg')
        if not ffmpeg_path:
            raise RuntimeError('找不到 FFmpeg')
        command = [
            ffmpeg_path, '-y', '-i', source_path,
            '-map', '0:v:0', '-map', '0:a?',
            '-c:v', 'copy', '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11',
            '-c:a', 'aac', '-movflags', '+faststart', output_path,
        ]
        result = subprocess.run(
            command, capture_output=True, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
        )
        if result.returncode != 0 or not os.path.exists(output_path):
            raise RuntimeError('FFmpeg 音量平衡失敗')
        shutil.move(output_path, final_path)
        broadcast_log(f'✅ 音量平衡完成：{filename}')
        socketio.emit('refresh_list')
        return json.dumps({'success': True, 'filename': filename}, ensure_ascii=False)
    except (OSError, RuntimeError) as error:
        broadcast_log(f'❌ 音量平衡失敗：{error}')
        return json.dumps({'error': str(error)}, ensure_ascii=False), 400
    finally:
        is_processing = False
        socketio.emit('task_status', {'status': 'idle'})
        shutil.rmtree(job_dir, ignore_errors=True)

def save_subtitle(song_filename, content, subtitle_extension):
    """Convert subtitle text and save it as the matching song's WebVTT file."""
    converted_content = convert_to_webvtt(content, subtitle_extension)
    output_name = os.path.splitext(song_filename)[0] + '.vtt'
    with open(os.path.join(SONGS_DIR, output_name), 'w', encoding='utf-8', newline='\n') as output_file:
        output_file.write(converted_content)
    return output_name

def convert_to_webvtt(content, subtitle_extension):
    """Convert SRT, LRC, or VTT text into browser-compatible WebVTT text."""
    if subtitle_extension == 'srt':
        return srt_to_webvtt(content)
    if subtitle_extension == 'lrc':
        return lrc_to_webvtt(content)
    if not content.lstrip().startswith('WEBVTT'):
        return 'WEBVTT\n\n' + content
    return content

def detect_subtitle_format(content, extension=''):
    """Detect a subtitle format from content, using the extension only as fallback."""
    normalized = content.strip()
    if re.match(r'^WEBVTT(?:\s|$)', normalized, re.IGNORECASE):
        return 'vtt'
    if re.search(r'^\s*\[\d{1,3}:\d{2}(?:[.:]\d{1,3})?\]', normalized, re.MULTILINE):
        return 'lrc'
    if re.search(r'\d{2}:\d{2}:\d{2}[,.]\d{3}\s+-->', normalized):
        return 'srt'
    if extension in SUBTITLE_EXTENSIONS:
        return extension
    raise ValueError('無法判斷字幕格式，請確認內容是 SRT、LRC 或 VTT。')

def srt_to_webvtt(content):
    """Convert SRT timestamp separators to the WebVTT format."""
    lines = content.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    converted = ['WEBVTT', '']
    for line in lines:
        if re.match(r'^\s*\d{2}:\d{2}:\d{2},\d{3}\s+-->\s+\d{2}:\d{2}:\d{2},\d{3}', line):
            line = line.replace(',', '.')
        converted.append(line)
    return '\n'.join(converted)

def lrc_to_webvtt(content):
    """Convert LRC minute-second tags into one WebVTT cue per timestamp."""
    lines = content.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    converted = ['WEBVTT', '']
    timestamp_pattern = re.compile(r'\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\](.*)')
    cues = []
    for line in lines:
        match = timestamp_pattern.match(line.strip())
        if not match:
            continue
        minutes, seconds, fraction, text = match.groups()
        milliseconds = int((fraction or '0').ljust(3, '0')[:3])
        start_ms = (int(minutes) * 60 + int(seconds)) * 1000 + milliseconds
        cues.append((start_ms, text.strip()))
    cues.sort(key=lambda cue: cue[0])
    for index, (start_ms, text) in enumerate(cues):
        end_ms = cues[index + 1][0] if index + 1 < len(cues) else start_ms + 4000
        if end_ms <= start_ms:
            end_ms = start_ms + 1000
        converted.extend([
            f'{format_vtt_time(start_ms)} --> {format_vtt_time(end_ms)}',
            text,
            '',
        ])
    if not cues:
        raise ValueError('找不到有效的 LRC 時間標記')
    return '\n'.join(converted)

def format_vtt_time(milliseconds):
    """Format milliseconds as a WebVTT HH:MM:SS.mmm timestamp."""
    total_seconds, millis = divmod(max(0, milliseconds), 1000)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f'{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}'

# ------------------------------------------
# SocketIO 事件處理 & 待播清單
# ------------------------------------------
playlist_queue = []
subtitle_visible = False
subtitle_font_size = 100
qr_visible = True

def broadcast_current_song():
    """Broadcast the current song and its subtitle presentation state to all clients."""
    filename = playlist_queue[0] if playlist_queue else ''
    socketio.emit('current_song', {
        'filename': filename,
        'visible': subtitle_visible,
        'font_size': subtitle_font_size,
    })

@socketio.on('connect')
def handle_connect():
    """Send the current queue to each newly connected client."""
    emit('update_queue', playlist_queue)
    emit('current_song', {
        'filename': playlist_queue[0] if playlist_queue else '',
        'visible': subtitle_visible,
        'font_size': subtitle_font_size,
    })
    emit('qr_visibility', {'visible': qr_visible})

@socketio.on('set_qr_visibility')
def handle_qr_visibility(data):
    """Update and broadcast whether playback screens show the remote QR Code."""
    global qr_visible
    qr_visible = bool(data.get('visible')) if isinstance(data, dict) else True
    emit('qr_visibility', {'visible': qr_visible}, broadcast=True)

@socketio.on('add_to_queue')
def handle_add_queue(data):
    global subtitle_visible
    filename = data['filename']
    playlist_queue.append(filename)
    
    # 廣播更新所有設備上的歌單畫面
    emit('update_queue', playlist_queue, broadcast=True)
    emit('queue_song_added', {'filename': filename}, broadcast=True)
    
    # 如果清單裡面只有剛點的這首歌，代表目前沒有歌在播，立刻開始播放
    if len(playlist_queue) == 1:
        subtitle_visible = False
        emit('play_video', _play_video_payload(filename), broadcast=True)
        broadcast_current_song()

@socketio.on('toggle_subtitle')
def handle_toggle_subtitle(data):
    """Toggle subtitles only for the song currently playing."""
    global subtitle_visible
    filename = os.path.basename(data.get('filename', '')) if isinstance(data, dict) else ''
    if not playlist_queue or filename != playlist_queue[0]:
        return
    subtitle_path = os.path.join(SONGS_DIR, os.path.splitext(filename)[0] + '.vtt')
    if not os.path.exists(subtitle_path):
        return
    subtitle_visible = not subtitle_visible
    emit('subtitle_state', {
        'filename': filename,
        'visible': subtitle_visible,
        'font_size': subtitle_font_size,
    }, broadcast=True)
    broadcast_current_song()

@socketio.on('set_subtitle_font_size')
def handle_set_subtitle_font_size(data):
    """Update and broadcast the shared subtitle font size in percent."""
    global subtitle_font_size
    try:
        requested_size = int(data.get('font_size', 100)) if isinstance(data, dict) else 100
    except (TypeError, ValueError):
        return
    if requested_size not in {80, 100, 120}:
        return
    subtitle_font_size = requested_size
    emit('subtitle_state', {
        'filename': playlist_queue[0] if playlist_queue else '',
        'visible': subtitle_visible,
        'font_size': subtitle_font_size,
    }, broadcast=True)
    broadcast_current_song()

@socketio.on('remove_from_queue')
def handle_remove_from_queue(data):
    """Remove a queued song by index while protecting the currently playing song."""
    try:
        queue_index = int(data.get('index', -1))
    except (AttributeError, TypeError, ValueError):
        return
    if queue_index <= 0 or queue_index >= len(playlist_queue):
        return
    playlist_queue.pop(queue_index)
    emit('update_queue', playlist_queue, broadcast=True)

@socketio.on('song_ended')
def handle_song_ended():
    global subtitle_visible
    if len(playlist_queue) > 0:
        # 移除剛剛唱完的那首歌
        playlist_queue.pop(0) 
        subtitle_visible = False
        emit('update_queue', playlist_queue, broadcast=True)
        
        # 檢查是否還有下一首
        if len(playlist_queue) > 0:
            next_song = playlist_queue[0]
            emit('play_video', _play_video_payload(next_song), broadcast=True)
            broadcast_current_song()
        else:
            # 沒歌了，停止畫面並回到待機狀態
            emit('stop_video', broadcast=True)
            broadcast_current_song()

@socketio.on('control')
def handle_control(action):
    if action == 'cut':
        # 按下切歌時，等於強迫觸發「歌曲結束」事件，讓系統自動播下一首
        handle_song_ended()
    else:
        # 其他指令 (例如 pause) 照常發送
        emit('command', action, broadcast=True)

# ------------------------------------------
# (以下原本的音效與下載事件保留不動)
@socketio.on('control_effect')
def handle_effect(data):
    emit('apply_effect', data, broadcast=True)

# ...後面的 @socketio.on('change_track') 等等都不用動...

@socketio.on('control_effect')
def handle_effect(data):
    # 收到音量或升降 KEY 指令後，同步廣播給所有設備（包含一體機自己）
    emit('apply_effect', data, broadcast=True)

@socketio.on('change_track')
def handle_track(mode):
    emit('set_audio', mode, broadcast=True)

is_processing = False


# ==========================================
# Spleeter 獨立進程處理函式
# ==========================================
def _run_spleeter_process(input_path, output_dir):
    """
    這個函式會在一個完全獨立的 Python 進程中執行。
    結束時作業系統會強制清空此進程佔用的 TensorFlow 記憶體。
    """
    try:
        from spleeter.separator import Separator
        # 初始化並執行分離
        separator = Separator('spleeter:2stems')
        separator.separate_to_file(input_path, output_dir)
    except Exception:
        import traceback
        with open(os.path.join(output_dir, "spleeter_error.log"), "w", encoding="utf-8") as error_file:
            error_file.write(traceback.format_exc())
        raise




@socketio.on('start_download')
def handle_start_download(data):
    global is_processing
    if is_processing:
        broadcast_log("⚠️ 系統正在處理其他歌曲，請稍候。")
        return
    
    url = data.get('url')
    title = data.get('title')
    ai_engine = data.get('ai_engine', 'spleeter')
    normalize_volume = data.get('normalize_volume', True) is not False
    if ai_engine not in ('spleeter', 'mdxnet'):
        broadcast_log(f"❌ 不支援的 AI 去人聲引擎：{ai_engine}")
        return
    if ai_engine == 'mdxnet':
        broadcast_log("❌ MDX-Net 尚未安裝，請先使用 Spleeter，或完成 ToDo.md 的 MDX-Net 測試階段。")
        return
    
    def run_process():
        global is_processing
        is_processing = True
        socketio.emit('task_status', {'status': 'busy'})
        
        processor = KTVProcessor(log_cb=broadcast_log)
        output_filename = processor.process_song(url, title, ai_engine, normalize_volume)
        
        if output_filename:
            socketio.emit('refresh_list')
        
        is_processing = False
        socketio.emit('task_status', {'status': 'idle'})

    broadcast_log("=== 開始新任務 ===")
    threading.Thread(target=run_process, daemon=True).start()

@socketio.on('update_ytdlp')
def handle_update_ytdlp():
    def run_update():
        socketio.emit('task_status', {'status': 'busy'})
        broadcast_log("開始更新 yt-dlp 核心...")
        try:
            cmd = get_ytdlp_command() + ["-U"]
            result = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            broadcast_log(result.stdout)
            if result.stderr: broadcast_log(result.stderr)
            broadcast_log("✅ yt-dlp 更新程序結束。")
        except Exception as e:
            broadcast_log(f"❌ 更新失敗: {str(e)}")
        finally:
            socketio.emit('task_status', {'status': 'idle'})

    threading.Thread(target=run_update, daemon=True).start()

def run_server_thread():
    try:
        print("🚀 準備啟動 Flask 伺服器...")
        
        # 【關鍵防護】強制關閉 Flask 雞婆的啟動橫幅 (Banner) 與日誌，從根本拔除報錯源頭
        import logging
        from flask import cli
        cli.show_server_banner = lambda *args, **kwargs: None  # 暴力閹割橫幅印出功能
        logging.getLogger('werkzeug').setLevel(logging.ERROR)  # 只允許印出重大錯誤
        
        cert_path, key_path = ensure_tls_certificate()
        print(f"🔒 HTTPS 服務已啟用：https://{LOCAL_IP}:{PORT}")
        socketio.run(app, host='0.0.0.0', port=PORT, debug=False,
                 allow_unsafe_werkzeug=True, ssl_context=(cert_path, key_path))
    except Exception as e:
        import traceback
        print(f"❌ 伺服器啟動失敗: {e}")
        print(traceback.format_exc())

# ==========================================
# 核心處理類別
# ==========================================
class KTVProcessor:
    def __init__(self, log_cb):
        self.log = log_cb

    def sanitize_filename(self, name):
        return "".join([c for c in name if c not in r'\/:*?"<>|'])

    def process_song(self, url, manual_title, ai_engine='spleeter', normalize_volume=True):
        job_temp_dir = None
        try:
            safe_title = self.sanitize_filename(manual_title)
            self.log(f"目標歌曲：{safe_title}")

            job_id = str(int(time.time()))
            job_temp_dir = os.path.join(TEMP_BASE_DIR, job_id)
            os.makedirs(job_temp_dir, exist_ok=True)

            temp_input = os.path.join(job_temp_dir, "input.mp4")
            temp_output = os.path.join(job_temp_dir, "output.mp4")

            self.log("步驟 1/4: 下載影片...")
            ffmpeg_location = get_ffmpeg_location()
            cmd_dl = get_ytdlp_command() + ([
                "--ffmpeg-location", ffmpeg_location
            ] if ffmpeg_location else []) + [
                "--force-overwrites",  
                "--no-playlist",       
                "-f", "bestvideo[vcodec^=avc1][height<=1080]+bestaudio[ext=m4a]/bestvideo[ext=mp4][height<=1080]+best[ext=mp4][height<=1080]/best",
                "-o", temp_input, 
                url
            ]
            
            subprocess.run(
                cmd_dl, check=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
            )

            engine_names = {'spleeter': 'Spleeter', 'mdxnet': 'MDX-Net'}
            engine_name = engine_names.get(ai_engine)
            if engine_name is None:
                raise ValueError(f"不支援的 AI 去人聲引擎：{ai_engine}")
            self.log(f"步驟 2/4: AI 去人聲 ({engine_name})... (這需要一點時間)")
            
            # 【終極修復】PyInstaller 打包後沒有 spleeter.exe 可用 subprocess 呼叫。
            # 改用 multiprocessing 開啟獨立 Python 子進程執行 API。
            # 效果與 CLI 完全相同：進程結束後，OS 會強制回收 TensorFlow 記憶體！
            import multiprocessing
            p = multiprocessing.Process(target=_run_spleeter_process, args=(temp_input, job_temp_dir))
            p.start()
            p.join() # 等待進程執行完畢
            
            if p.exitcode != 0:
                error_log = os.path.join(job_temp_dir, "spleeter_error.log")
                if os.path.exists(error_log):
                    with open(error_log, encoding="utf-8") as error_file:
                        self.log(error_file.read())
                raise Exception(f"Spleeter 分離失敗，子進程異常結束 (Exit code: {p.exitcode})")
            
            # Spleeter CLI 預設會建立一個以輸入檔名為名稱的資料夾，所以路徑稍微改變
            base_name = os.path.splitext(os.path.basename(temp_input))[0] # 會得到 "input"
            voc_path = os.path.join(job_temp_dir, base_name, "vocals.wav")
            acc_path = os.path.join(job_temp_dir, base_name, "accompaniment.wav")

            if not os.path.exists(voc_path) or not os.path.exists(acc_path):
                raise Exception("Spleeter 分離失敗，找不到音軌檔")

            self.log("步驟 3/4: 合成六聲道（原聲 / 導唱 / 伴奏）...")
            ffmpeg_path = os.path.join(ffmpeg_location, 'ffmpeg.exe') if ffmpeg_location else shutil.which('ffmpeg')
            ffprobe_path = get_ffprobe_path(ffmpeg_path) if ffmpeg_path else None
            if not ffmpeg_path or not ffprobe_path:
                raise Exception("找不到 FFmpeg 或 FFprobe")
            _create_six_channel_mp4(
                ffmpeg_path, ffprobe_path, temp_input, voc_path, acc_path,
                temp_output, normalize_volume,
            )

            self.log(f"步驟 4/4: 儲存為 {safe_title}.mp4")
            final = os.path.join(SONGS_DIR, f"{safe_title}.mp4")
            
            if os.path.exists(final):
                final = os.path.join(SONGS_DIR, f"{safe_title}_{job_id}.mp4")

            shutil.move(temp_output, final)
            
            self.log("✅ 製作完成！已自動同步至歌單（六聲道：原聲 / 導唱 / 伴奏）。")
            return os.path.basename(final)

        except subprocess.CalledProcessError as e:
            self.log(f"❌ 執行失敗 (Code {e.returncode})")
            return None
        except Exception as e:
            self.log(f"❌ 錯誤: {e}")
            return None
        finally:
            if job_temp_dir and os.path.exists(job_temp_dir):
                try:
                    shutil.rmtree(job_temp_dir, ignore_errors=True)
                except:
                    pass 

# ==========================================
# 本機 GUI 
# ==========================================
class ServerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"ianAutoKTV {APP_VERSION}")
        self.geometry("450x500") # 稍微拉高一點放日誌框
        self.configure(bg="#f4f4f9")
        
        tk.Label(self, text=f"🎤 KTV 系統運作中 {APP_VERSION}", font=("Microsoft JhengHei", 20, "bold"), fg="#4CAF50", bg="#f4f4f9").pack(pady=10)
        
        info_frame = tk.Frame(self, bg="white", bd=1, relief="solid")
        info_frame.pack(fill="x", padx=20, pady=5)
        
        self.create_clickable_link(info_frame, "📺 播放端 (電視用)", f"https://{LOCAL_IP}:{PORT}/player", "blue")
        self.create_clickable_link(info_frame, "📱 遙控端 (手機用)", f"https://{LOCAL_IP}:{PORT}/remote", "#d32f2f")
        self.create_clickable_link(info_frame, "🕹️ 一體機 (單機用)", f"https://{LOCAL_IP}:{PORT}/combo", "#9C27B0")
        self.create_clickable_link(info_frame, "⚙️ 管理端 (加歌用)", f"https://{LOCAL_IP}:{PORT}/admin", "#F57C00")

        stat_frame = tk.Frame(self, bg="#f4f4f9")
        stat_frame.pack(fill="x", padx=20, pady=5)
        
        self.lbl_count = tk.Label(stat_frame, text="總歌曲數: 載入中...", font=("Microsoft JhengHei", 12, "bold"), bg="#f4f4f9")
        self.lbl_count.pack(anchor="w")
        
        self.lbl_size = tk.Label(stat_frame, text="佔用空間: 載入中...", font=("Microsoft JhengHei", 12, "bold"), bg="#f4f4f9")
        self.lbl_size.pack(anchor="w", pady=5)

        # 增加一個實體的 GUI 日誌框，用來接聽攔截到的錯誤訊息
        self.log_txt = tk.Text(self, height=8, state="disabled", bg="#222", fg="#0f0", font=("Consolas", 9))
        self.log_txt.pack(fill="both", expand=True, padx=20, pady=10)
        
        self.update_stats()
        
        # 啟動背景佇列監聽器
        self.check_log_queue()

    def create_clickable_link(self, parent, text_prefix, url, color):
        frame = tk.Frame(parent, bg="white")
        frame.pack(pady=2, anchor="w", padx=10)
        tk.Label(frame, text=f"{text_prefix}: ", font=("Consolas", 11), bg="white").pack(side="left")
        link_lbl = tk.Label(frame, text=url, font=("Consolas", 11, "underline"), fg=color, bg="white", cursor="hand2")
        link_lbl.pack(side="left")
        link_lbl.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))

    def update_stats(self):
        try:
            songs = [f for f in os.listdir(SONGS_DIR) if f.endswith('.mp4')]
            count = len(songs)
            total_size = sum(os.path.getsize(os.path.join(SONGS_DIR, f)) for f in songs)
            size_mb = total_size / (1024 * 1024)
            
            self.lbl_count.config(text=f"🎵 總歌曲數: {count} 首")
            self.lbl_size.config(text=f"💾 佔用空間: {size_mb:.2f} MB")
        except Exception as e:
            pass
        self.after(5000, self.update_stats)

    def check_log_queue(self):
        """每 100 毫秒檢查一次佇列，把背景的文字寫進 GUI 日誌框"""
        try:
            while not system_log_queue.empty():
                msg = system_log_queue.get_nowait()
                self.log_txt.config(state="normal")
                self.log_txt.insert("end", msg + "\n")
                self.log_txt.see("end")
                self.log_txt.config(state="disabled")
        except Exception:
            pass
        self.after(100, self.check_log_queue)

if __name__ == "__main__":
    # 【關鍵】多進程保護必須放在 if __name__ == "__main__": 的第一行
    multiprocessing.freeze_support()

    if get_ffmpeg_location() is None:
        try:
            messagebox.showerror("錯誤", "找不到 FFmpeg\n請將 ffmpeg 資料夾放在程式同一目錄")
        except:
            print("找不到 FFmpeg")
    else:
        t = threading.Thread(target=run_server_thread)
        t.daemon = True
        t.start()
        
        app = ServerApp()
        app.mainloop()