"""Regression tests for the loopback-only Google Drive download prototype."""

import io
import json
import os
import tempfile
import time
import unittest
import urllib.error
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from flask import Flask

import google_drive_prototype as drive


class FakeDriveResponse:
    """Provide a closeable, chunk-readable response without network access."""

    def __init__(self, content):
        self._content = io.BytesIO(content)

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        self._content.close()

    def read(self, size=-1):
        return self._content.read(size)


class GoogleDriveDownloadTests(unittest.TestCase):
    """Exercise selected-folder validation and atomic original-media saves."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app = Flask(__name__)
        self.app.config["DRIVE_PROTOTYPE_DOWNLOAD_DIR"] = self.temp_dir.name
        self.app.config["GOOGLE_DRIVE_ACCOUNT_PATH"] = os.path.join(self.temp_dir.name, "account.bin")
        self.app.config["GOOGLE_DRIVE_DEPLOY_PATH"] = os.path.join(self.temp_dir.name, "deploy.json")
        drive.register_google_drive_prototype(self.app)
        self.client = self.app.test_client()
        self.flow_id = "test-flow"
        self.folder_id = "selected-folder"
        with drive._flow_lock:
            drive._flows.clear()
            drive._flows[self.flow_id] = {
                "created_at": time.time(),
                "status": "listed",
                "access_token": "test-access-token",
                "access_token_expires_at": time.time() + 300,
                "folder_id": self.folder_id,
                "download_in_progress": False,
            }

    def tearDown(self):
        with drive._flow_lock:
            drive._flows.clear()
        self.temp_dir.cleanup()

    def _folder_metadata(self):
        return {
            "id": self.folder_id,
            "mimeType": drive.DRIVE_FOLDER_MIME_TYPE,
            "driveId": "shared-drive",
        }

    def _song_metadata(self, content, parents=None):
        return {
            "id": "song-file-id",
            "name": "驗收歌曲.mp4",
            "mimeType": "video/mp4",
            "size": str(len(content)),
            "parents": parents if parents is not None else [self.folder_id],
            "driveId": "shared-drive",
        }

    def _post_download(self, file_id="song-file-id"):
        return self.client.post(
            "/api/drive-prototype/download",
            json={"flow_id": self.flow_id, "file_id": file_id},
        )

    @staticmethod
    def _http_error(status, reason):
        """Build a Google-shaped HTTP error without contacting the network."""
        body = json.dumps({"error": {"errors": [{"reason": reason}]}}).encode("utf-8")
        return urllib.error.HTTPError(
            "https://www.googleapis.com/drive/v3/files",
            status,
            "test",
            {},
            io.BytesIO(body),
        )

    def test_download_streams_original_media_and_uses_hashed_filename(self):
        """A verified child is saved completely without exposing its Drive name as a path."""
        content = b"original MP4 media"
        with patch.object(
            drive,
            "_google_api_get",
            side_effect=[self._folder_metadata(), self._song_metadata(content)],
        ), patch.object(
            drive.urllib.request,
            "urlopen",
            return_value=FakeDriveResponse(content),
        ) as media_request:
            response = self._post_download()

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["size"], len(content))
        self.assertEqual(payload["name"], "驗收歌曲.mp4")
        self.assertTrue(payload["saved_as"].endswith(".mp4"))
        self.assertNotIn("驗收歌曲", payload["saved_as"])
        with open(os.path.join(self.temp_dir.name, payload["saved_as"]), "rb") as saved_file:
            self.assertEqual(saved_file.read(), content)
        with open(os.path.join(self.temp_dir.name, drive.DRIVE_DOWNLOAD_METADATA_FILENAME), "r", encoding="utf-8") as metadata_file:
            metadata = json.load(metadata_file)
        self.assertEqual(metadata["song-file-id"]["file_id"], "song-file-id")
        self.assertEqual(metadata["song-file-id"]["name"], "驗收歌曲.mp4")
        self.assertEqual(metadata["song-file-id"]["saved_as"], payload["saved_as"])
        self.assertEqual(metadata["song-file-id"]["public_filename"], "驗收歌曲.mp4")
        self.assertEqual(
            drive.get_downloaded_song_path(self.temp_dir.name, "驗收歌曲.mp4"),
            os.path.join(self.temp_dir.name, payload["saved_as"]),
        )
        request = media_request.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer test-access-token")
        self.assertEqual(parse_qs(urlparse(request.full_url).query)["alt"], ["media"])

    def test_drive_api_retries_rate_limit_once(self):
        """429 is retried with backoff and succeeds without exposing response data."""
        with patch.object(
            drive.urllib.request,
            "urlopen",
            side_effect=[self._http_error(429, "rateLimitExceeded"), FakeDriveResponse(b'{"ok": true}')],
        ) as request, patch.object(drive.time, "sleep") as sleep:
            payload = drive._google_api_get("https://example.test/drive", "test-token")

        self.assertEqual(payload, {"ok": True})
        self.assertEqual(request.call_count, 2)
        sleep.assert_called_once()

    def test_drive_api_does_not_retry_permission_forbidden(self):
        """A permission 403 is terminal and must not cause repeated requests."""
        with patch.object(
            drive.urllib.request,
            "urlopen",
            side_effect=self._http_error(403, "insufficientFilePermissions"),
        ) as request, patch.object(drive.time, "sleep") as sleep:
            with self.assertRaises(drive.DriveApiError) as raised:
                drive._google_api_get("https://example.test/drive", "test-token")

        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(request.call_count, 1)
        sleep.assert_not_called()

    def test_media_download_retries_rate_limit_before_publishing(self):
        """A transient media failure retries the complete download and publishes only once."""
        content = b"original MP4 media"
        with patch.object(
            drive,
            "_google_api_get",
            side_effect=[self._folder_metadata(), self._song_metadata(content)],
        ), patch.object(
            drive.urllib.request,
            "urlopen",
            side_effect=[self._http_error(429, "rateLimitExceeded"), FakeDriveResponse(content)],
        ) as media_request, patch.object(drive.time, "sleep") as sleep:
            response = self._post_download()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(media_request.call_count, 2)
        sleep.assert_called_once()

    def test_lan_library_listing_returns_folder_songs_without_token(self):
        """LAN remotes receive only selected-folder metadata, never an access token."""
        listing = {
            "folder": {"id": self.folder_id, "name": "Songs"},
            "diagnostics": {"drive_type": "my_drive", "corpus": "user"},
            "songs": [{
                "id": "song-file-id",
                "name": "驗收歌曲.mp4",
                "mimeType": "video/mp4",
                "size": "18",
            }],
        }
        with patch.object(
            drive,
            "_stored_library_access_token",
            return_value=({"folder_id": self.folder_id}, "secret-access-token"),
        ), patch.object(drive, "_list_folder_children", return_value=listing):
            response = self.client.get(
                "/api/drive/library-songs",
                environ_base={"REMOTE_ADDR": "192.168.1.20"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["songs"][0]["id"], "song-file-id")
        self.assertNotIn("secret-access-token", json.dumps(payload))

    def test_lan_library_download_revalidates_and_returns_public_filename(self):
        """A remote download still binds the file ID to the saved folder before media access."""
        item = self._song_metadata(b"downloaded media")
        item["id"] = "song-file-id"
        saved_as = "downloaded-hash.mp4"

        def fake_download(_file_id, _token, _size, download_dir):
            with open(os.path.join(download_dir, saved_as), "wb") as media:
                media.write(b"downloaded media")
            return saved_as

        with patch.object(
            drive,
            "_stored_library_access_token",
            return_value=({"folder_id": self.folder_id}, "secret-access-token"),
        ), patch.object(drive, "_validate_drive_song", return_value=(item, len(b"downloaded media"))), patch.object(
            drive, "_download_drive_media", side_effect=fake_download,
        ) as download:
            response = self.client.post(
                "/api/drive/library-songs/download",
                json={"file_id": "song-file-id"},
                environ_base={"REMOTE_ADDR": "192.168.1.20"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["filename"], "驗收歌曲.mp4")
        download.assert_called_once_with(
            "song-file-id", "secret-access-token", len(b"downloaded media"), self.temp_dir.name,
        )

    def test_download_rejects_file_outside_selected_folder(self):
        """A valid Drive ID from another folder is rejected before media is requested."""
        content = b"private media"
        with patch.object(
            drive,
            "_google_api_get",
            side_effect=[
                self._folder_metadata(),
                self._song_metadata(content, parents=["different-folder"]),
            ],
        ), patch.object(drive.urllib.request, "urlopen") as media_request:
            response = self._post_download()

        self.assertEqual(response.status_code, 400)
        self.assertIn("直接子項目", response.get_json()["error"])
        media_request.assert_not_called()
        self.assertEqual(os.listdir(self.temp_dir.name), [])

    def test_download_rejects_invalid_file_id_before_drive_access(self):
        """A caller cannot use a path-like identifier to select an arbitrary Drive file."""
        with patch.object(drive, "_google_api_get") as metadata_request:
            response = self._post_download("../outside.mp4")

        self.assertEqual(response.status_code, 400)
        metadata_request.assert_not_called()
        self.assertEqual(os.listdir(self.temp_dir.name), [])

    def test_incomplete_media_is_removed_instead_of_published(self):
        """A truncated network response leaves neither a final file nor a partial file."""
        content = b"truncated"
        metadata = self._song_metadata(b"expected complete media")
        with patch.object(
            drive,
            "_google_api_get",
            side_effect=[self._folder_metadata(), metadata],
        ), patch.object(
            drive.urllib.request,
            "urlopen",
            return_value=FakeDriveResponse(content),
        ):
            response = self._post_download()

        self.assertEqual(response.status_code, 502)
        self.assertIn("未完整", response.get_json()["error"])
        self.assertEqual(os.listdir(self.temp_dir.name), [])

    def test_listed_folder_and_short_lived_token_remain_for_download(self):
        """Listing binds the selected folder to its in-memory authorization flow."""
        with drive._flow_lock:
            flow = drive._flows[self.flow_id]
            flow.update({
                "status": "authorized",
                "token_claimed": True,
                "list_started": False,
            })
        listing = {
            "folder": {"id": self.folder_id, "name": "Songs"},
            "diagnostics": {"drive_type": "my_drive", "corpus": "user", "pages_read": 1},
            "direct_child_count": 1,
            "song_count": 1,
            "ignored_item_count": 0,
            "songs": [{"id": "song-file-id", "name": "驗收歌曲.mp4", "mimeType": "video/mp4"}],
        }
        with patch.object(drive, "_list_folder_children", return_value=listing):
            response = self.client.post(
                "/api/drive-prototype/files",
                json={"flow_id": self.flow_id, "folder_id": self.folder_id},
            )

        self.assertEqual(response.status_code, 200)
        with drive._flow_lock:
            flow = drive._flows[self.flow_id]
            self.assertEqual(flow["status"], "listed")
            self.assertEqual(flow["folder_id"], self.folder_id)
            self.assertEqual(flow["access_token"], "test-access-token")

    def test_download_endpoint_remains_loopback_only(self):
        """LAN clients cannot trigger downloads with the local prototype flow."""
        response = self.client.post(
            "/api/drive-prototype/download",
            json={"flow_id": self.flow_id, "file_id": "song-file-id"},
            environ_base={"REMOTE_ADDR": "192.168.1.20"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(os.listdir(self.temp_dir.name), [])

    def test_public_filename_is_safe_for_filename_based_playback(self):
        """Drive names with path characters are sanitized before entering the client API."""
        self.assertEqual(
            drive._safe_public_filename(r"..\outside:歌曲?.mp4", "song-file-id"),
            "outside_歌曲_.mp4",
        )

    def test_download_management_lists_and_clears_local_file(self):
        """The host-only management endpoint removes media and its source mapping together."""
        saved_as = "managed-song.mp4"
        with open(os.path.join(self.temp_dir.name, saved_as), "wb") as media:
            media.write(b"managed media")
        drive._save_download_metadata(self.temp_dir.name, {
            "managed-file-id": {
                "file_id": "managed-file-id",
                "name": "管理歌曲.mp4",
                "saved_as": saved_as,
                "public_filename": "管理歌曲.mp4",
                "size": 13,
            },
        })

        listing = self.client.get("/api/drive-prototype/downloads")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.get_json()["downloads"][0]["file_id"], "managed-file-id")

        cleared = self.client.post(
            "/api/drive-prototype/downloads/clear",
            json={"file_id": "managed-file-id"},
        )
        self.assertEqual(cleared.status_code, 200)
        self.assertFalse(os.path.exists(os.path.join(self.temp_dir.name, saved_as)))
        self.assertEqual(drive._load_download_metadata(self.temp_dir.name), {})

    def test_download_management_cannot_be_changed_from_lan(self):
        """LAN remotes cannot inspect detailed downloads or delete host media."""
        listing = self.client.get(
            "/api/drive-prototype/downloads",
            environ_base={"REMOTE_ADDR": "192.168.1.20"},
        )
        cleared = self.client.post(
            "/api/drive-prototype/downloads/clear",
            json={"all": True},
            environ_base={"REMOTE_ADDR": "192.168.1.20"},
        )
        self.assertEqual(listing.status_code, 403)
        self.assertEqual(cleared.status_code, 403)


if __name__ == "__main__":
    unittest.main()
