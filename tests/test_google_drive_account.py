"""Regression tests for persistent KTV Google account linking."""

import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch

from flask import Flask

import google_drive_account as account
import google_drive_prototype as drive


class GoogleDriveAccountTests(unittest.TestCase):
    """Cover deploy-config OAuth, DPAPI token storage, and LAN isolation."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app = Flask(__name__)
        self.deploy_path = os.path.join(self.temp_dir.name, "deploy.json")
        self.account_path = os.path.join(self.temp_dir.name, "account.bin")
        self.app.config["DRIVE_PROTOTYPE_DOWNLOAD_DIR"] = self.temp_dir.name
        self.app.config["GOOGLE_DRIVE_DEPLOY_PATH"] = self.deploy_path
        self.app.config["GOOGLE_DRIVE_ACCOUNT_PATH"] = self.account_path
        with open(self.deploy_path, "w", encoding="utf-8") as handle:
            json.dump({
                "oauth_client_id": "desktop-client.apps.googleusercontent.com",
                "oauth_client_secret": "deploy-secret",
                "picker_api_key": "AIzaTestKey",
                "project_number": "1234567890",
            }, handle)
        drive.register_google_drive_prototype(self.app)
        self.client = self.app.test_client()
        with drive._flow_lock:
            drive._flows.clear()

    def tearDown(self):
        with drive._flow_lock:
            drive._flows.clear()
        self.temp_dir.cleanup()

    def _save_linked_account(self, **overrides):
        state = {
            "refresh_token": "stored-refresh-token",
            "account_email": "ktv@example.com",
            "account_name": "KTV Host",
            "folder_id": "selected-folder",
            "folder_name": "KTV Songs",
            "drive_id": "",
            "auth_expired": False,
        }
        state.update(overrides)
        account.save_account_state(self.account_path, state)
        return state

    def test_dpapi_roundtrip_does_not_write_plaintext_refresh_token(self):
        """The account file on disk must not contain the refresh token in plaintext."""
        self._save_linked_account()
        with open(self.account_path, "rb") as handle:
            raw = handle.read()
        self.assertNotIn(b"stored-refresh-token", raw)
        loaded = account.load_account_state(self.account_path)
        self.assertEqual(loaded["refresh_token"], "stored-refresh-token")
        self.assertEqual(loaded["account_email"], "ktv@example.com")

    def test_library_status_hides_secrets_and_allows_lan(self):
        """LAN clients can see the shared library, but never tokens or client secrets."""
        self._save_linked_account()
        response = self.client.get(
            "/api/drive/library-status",
            environ_base={"REMOTE_ADDR": "192.168.1.20"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["linked"])
        self.assertEqual(payload["account_email"], "ktv@example.com")
        self.assertEqual(payload["folder_name"], "KTV Songs")
        serialized = json.dumps(payload)
        self.assertNotIn("stored-refresh-token", serialized)
        self.assertNotIn("deploy-secret", serialized)
        self.assertNotIn("AIzaTestKey", serialized)

    def test_unlink_and_oauth_start_are_loopback_only(self):
        """Zone-network remotes cannot change the KTV installation Google account."""
        self._save_linked_account()
        unlink = self.client.post(
            "/api/drive-prototype/unlink",
            json={},
            environ_base={"REMOTE_ADDR": "192.168.1.20"},
        )
        start = self.client.post(
            "/api/drive-prototype/oauth/start",
            json={"client_secret": "from-browser"},
            environ_base={"REMOTE_ADDR": "192.168.1.20"},
        )
        self.assertEqual(unlink.status_code, 403)
        self.assertEqual(start.status_code, 403)
        self.assertEqual(
            account.load_account_state(self.account_path)["refresh_token"],
            "stored-refresh-token",
        )

    def test_oauth_start_uses_deploy_config_not_request_body(self):
        """Browser-submitted Client Secret is ignored; only the host deploy file is used."""
        class ImmediateThread:
            last_args = None

            def __init__(self, target=None, args=(), kwargs=None, daemon=None):
                ImmediateThread.last_args = args

            def start(self):
                return

        class ImmediateTimer:
            def __init__(self, interval, function, args=None, kwargs=None):
                return

            def start(self):
                return

        with patch.object(drive.threading, "Thread", ImmediateThread), patch.object(
            drive.threading, "Timer", ImmediateTimer
        ):
            response = self.client.post(
                "/api/drive-prototype/oauth/start",
                json={
                    "client_id": "attacker.apps.googleusercontent.com",
                    "client_secret": "from-browser",
                    "picker_api_key": "AIzaBrowser",
                    "project_number": "1",
                },
            )
        self.assertEqual(response.status_code, 200)
        args = ImmediateThread.last_args
        # Thread args=(flow_id, client_id, client_secret, account_path)
        self.assertEqual(args[1], "desktop-client.apps.googleusercontent.com")
        self.assertEqual(args[2], "deploy-secret")
        self.assertEqual(args[3], self.account_path)
        payload = response.get_json()
        self.assertEqual(payload["picker_api_key"], "AIzaTestKey")
        self.assertNotIn("oauth_client_secret", payload)
        self.assertNotIn("client_secret", payload)

    def test_oauth_start_requires_deploy_file(self):
        """Linking cannot begin until the operator places the host deploy file."""
        os.remove(self.deploy_path)
        response = self.client.post("/api/drive-prototype/oauth/start", json={})
        self.assertEqual(response.status_code, 400)
        self.assertIn("部署檔", response.get_json()["error"])

    def test_local_unlink_clears_saved_refresh_token(self):
        """Host unlink deletes the encrypted account file for this installation."""
        self._save_linked_account()
        response = self.client.post("/api/drive-prototype/unlink", json={})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(account.load_account_state(self.account_path))

    def test_listing_persists_selected_folder_without_exposing_token(self):
        """A successful first-layer listing saves folder metadata onto the linked account."""
        self._save_linked_account(folder_id="", folder_name="")
        flow_id = "test-flow"
        with drive._flow_lock:
            drive._flows[flow_id] = {
                "created_at": time.time(),
                "status": "authorized",
                "access_token": "test-access-token",
                "token_claimed": True,
                "list_started": False,
                "download_in_progress": False,
            }
        listing = {
            "folder": {"id": "new-folder", "name": "驗收歌庫"},
            "diagnostics": {"drive_type": "my_drive", "corpus": "user", "pages_read": 1},
            "direct_child_count": 1,
            "song_count": 1,
            "ignored_item_count": 0,
            "songs": [{"id": "song-file-id", "name": "驗收歌曲.mp4", "mimeType": "video/mp4"}],
        }
        with patch.object(drive, "_list_folder_children", return_value=listing):
            response = self.client.post(
                "/api/drive-prototype/files",
                json={"flow_id": flow_id, "folder_id": "new-folder"},
            )
        self.assertEqual(response.status_code, 200)
        saved = account.load_account_state(self.account_path)
        self.assertEqual(saved["folder_id"], "new-folder")
        self.assertEqual(saved["folder_name"], "驗收歌庫")
        self.assertEqual(saved["refresh_token"], "stored-refresh-token")
        self.assertNotIn("refresh_token", response.get_json())

    def test_picker_start_marks_expired_on_invalid_grant(self):
        """A revoked refresh token keeps folder metadata and asks the host to sign in again."""
        self._save_linked_account()
        with patch.object(
            drive,
            "_refresh_access_token",
            side_effect=drive.OAuthFlowError("Google OAuth 權杖交換失敗（HTTP 400，invalid_grant）：授權碼已失效。"),
        ):
            response = self.client.post("/api/drive-prototype/picker/start", json={})
        self.assertEqual(response.status_code, 401)
        self.assertIn("重新登入", response.get_json()["error"])
        saved = account.load_account_state(self.account_path)
        self.assertTrue(saved["auth_expired"])
        self.assertEqual(saved["folder_name"], "KTV Songs")

    def test_merge_linked_account_clears_folder_when_email_changes(self):
        """A different Google account on the same KTV host does not keep the previous folder."""
        merged = account.merge_linked_account(
            {
                "account_email": "old@example.com",
                "folder_id": "old-folder",
                "folder_name": "Old",
                "drive_id": "",
            },
            "new-refresh",
            {"email": "new@example.com", "name": "New"},
        )
        self.assertEqual(merged["refresh_token"], "new-refresh")
        self.assertEqual(merged["folder_id"], "")
        self.assertEqual(merged["account_email"], "new@example.com")


if __name__ == "__main__":
    unittest.main()
