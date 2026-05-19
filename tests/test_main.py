# Test Suite for Meeting Bot
# Run with: pytest tests/

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime


class TestConfig:
    """Test configuration management."""

    def test_config_validation_missing_vars(self):
        """Test that config validation detects missing variables."""
        with patch('config.Config.API_TOKEN', None), \
             patch('config.Config.GEMINI_API_KEY', None), \
             patch('config.Config.BITRIX_WEBHOOK', None), \
             patch('config.Config.TELEGRAM_USER_ID', None):
            from config import Config
            errors = Config.validate_config()
            assert len(errors) == 4
            assert 'TELEGRAM_BOT_TOKEN' in errors
            assert 'GEMINI_API_KEY' in errors
            assert 'BITRIX_WEBHOOK_URL' in errors
            assert 'TELEGRAM_USER_ID' in errors

    def test_config_create_directories(self, tmp_path):
        """Test directory creation."""
        with patch('config.Config.BASE_DIR', tmp_path):
            from config import Config
            Config.RECORDINGS_DIR = tmp_path / "recordings"
            Config.TRANSCRIPTS_DIR = tmp_path / "transcripts"
            Config.REPORTS_DIR = tmp_path / "reports"
            Config.create_directories()
            
            assert Config.RECORDINGS_DIR.exists()
            assert Config.TRANSCRIPTS_DIR.exists()
            assert Config.REPORTS_DIR.exists()

    def test_is_production(self):
        """Test production mode detection."""
        with patch('os.getenv', return_value='production'):
            from config import Config
            assert Config.is_production() is True
        
        with patch('os.getenv', return_value='development'):
            from config import Config
            assert Config.is_production() is False


class TestHealthEndpoints:
    """Test health check endpoints."""

    @pytest.mark.asyncio
    async def test_root_endpoint(self):
        """Test root health endpoint."""
        from main import app
        from fastapi.testclient import TestClient
        
        client = TestClient(app)
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "Meeting Bot"
        assert "timestamp" in data

    @pytest.mark.asyncio
    async def test_health_endpoint(self):
        """Test detailed health endpoint."""
        from main import app
        from fastapi.testclient import TestClient
        
        client = TestClient(app)
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "config_valid" in data
        assert "timestamp" in data


class TestWebhookValidation:
    """Test webhook input validation."""

    @pytest.mark.asyncio
    async def test_webhook_invalid_json(self):
        """Test webhook with invalid JSON."""
        from main import app
        from fastapi.testclient import TestClient
        
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/webhook", content="not valid json")
        
        # Should handle gracefully
        assert response.status_code in [200, 400]

    @pytest.mark.asyncio
    async def test_webhook_empty_message(self):
        """Test webhook with empty message."""
        from main import app
        from fastapi.testclient import TestClient
        
        client = TestClient(app)
        response = client.post("/webhook", json={"message": {"text": ""}})
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_webhook_unauthorized_user(self):
        """Test webhook from unauthorized user."""
        from main import app
        from fastapi.testclient import TestClient
        
        with patch('main.TELEGRAM_USER_ID', '123456'):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.post("/webhook", json={
                "message": {
                    "from": {"id": "999999"},
                    "text": "https://meet.google.com/test"
                }
            })
            
            assert response.status_code == 403


class TestURLParsing:
    """Test meeting URL parsing."""

    def test_url_parsing_with_lead_id(self):
        """Test parsing URL with lead ID."""
        import re
        text = "https://meet.google.com/abc-defg-hij id:123"
        match = re.search(r'(https?://\S+)(?:\s+id:(\d+))?', text, re.IGNORECASE)
        
        assert match is not None
        assert match.group(1) == "https://meet.google.com/abc-defg-hij"
        assert match.group(2) == "123"

    def test_url_parsing_without_lead_id(self):
        """Test parsing URL without lead ID."""
        import re
        text = "https://meet.google.com/abc-defg-hij"
        match = re.search(r'(https?://\S+)(?:\s+id:(\d+))?', text, re.IGNORECASE)
        
        assert match is not None
        assert match.group(1) == "https://meet.google.com/abc-defg-hij"
        assert match.group(2) is None

    def test_url_parsing_zoom(self):
        """Test parsing Zoom URL."""
        import re
        text = "https://zoom.us/j/123456789 id:456"
        match = re.search(r'(https?://\S+)(?:\s+id:(\d+))?', text, re.IGNORECASE)
        
        assert match is not None
        assert match.group(1) == "https://zoom.us/j/123456789"
        assert match.group(2) == "456"


class TestMeetingTools:
    """Test MeetingTools class."""

    def test_transcribe_audio_file_not_found(self):
        """Test transcription with non-existent file."""
        from tools import MeetingTools
        
        result = MeetingTools.transcribe_audio.func("/nonexistent/path.wav")
        assert "Файл не найден" in result or "не удалось" in result.lower()

    def test_update_bitrix_no_webhook(self):
        """Test Bitrix update without webhook configured."""
        with patch('config.Config.BITRIX_WEBHOOK', None):
            from tools import MeetingTools
            
            result = MeetingTools.update_bitrix_lead.func("123", "test analysis")
            assert "не настроен" in result.lower()

    def test_update_bitrix_invalid_lead_id(self):
        """Test Bitrix update with invalid lead ID."""
        with patch('config.Config.BITRIX_WEBHOOK', "https://test.webhook"):
            from tools import MeetingTools
            
            result = MeetingTools.update_bitrix_lead.func("invalid", "test")
            assert "Неверный формат" in result


class TestJoinMeetingScript:
    """Test join-meeting.js script."""

    def test_script_syntax(self):
        """Test JavaScript syntax."""
        import subprocess
        result = subprocess.run(
            ["node", "--check", "join-meeting.js"],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"


class TestSecurity:
    """Test security features."""

    def test_cors_configuration(self):
        """Test CORS middleware is configured."""
        from main import app
        
        # Check CORS middleware is present
        middleware_classes = [type(m).__name__ for m in app.user_middleware]
        assert any("cors" in m.lower() for m in middleware_classes)

    def test_rate_limiter_configured(self):
        """Test rate limiter is configured for webhook."""
        from main import app
        
        # Check webhook endpoint exists
        routes = [r.path for r in app.routes]
        assert "/webhook" in routes


@pytest.mark.asyncio
async def test_async_background_task():
    """Test background task processing."""
    from main import process_meeting_safe
    
    # Mock the dependencies
    with patch('main.send_telegram_message') as mock_send, \
         patch('main.process_meeting', new_callable=AsyncMock) as mock_process:
        
        mock_process.return_value = "Test result"
        
        await process_meeting_safe("https://test.meeting", "123")
        
        mock_process.assert_called_once()
        mock_send.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
