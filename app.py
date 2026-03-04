"""
Update Server для ManekiTerminal с поддержкой каналов (production/testing)
"""
from flask import Flask, jsonify, send_file, request
from pathlib import Path
import json

app = Flask(__name__)

# Конфигурация
RELEASES_DIR = Path("releases")
RELEASES_DIR.mkdir(exist_ok=True)


class ReleaseManager:
    """Управление релизами с поддержкой каналов"""

    CHANNELS = ['production', 'testing']
    DEFAULT_CHANNEL = 'production'

    def __init__(self, releases_dir: Path):
        self.releases_dir = releases_dir
        self._ensure_channels()

    def _ensure_channels(self):
        """Создать директории для каналов"""
        for channel in self.CHANNELS:
            channel_dir = self.releases_dir / channel
            channel_dir.mkdir(exist_ok=True)

    def _validate_channel(self, channel: str) -> str:
        """Валидация канала"""
        if not channel or channel not in self.CHANNELS:
            return self.DEFAULT_CHANNEL
        return channel

    def get_latest_release(self, channel: str = None) -> dict:
        """Получить последний релиз Terminal для канала"""
        channel = self._validate_channel(channel)
        manifest_file = self.releases_dir / channel / "latest.json"

        if not manifest_file.exists():
            return None

        with open(manifest_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            data['channel'] = channel
            return data

    def get_release(self, version: str, channel: str = None) -> dict:
        """Получить конкретный релиз Terminal"""
        channel = self._validate_channel(channel)
        manifest_file = self.releases_dir / channel / version / "version.json"

        if not manifest_file.exists():
            return None

        with open(manifest_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            data['channel'] = channel
            return data

    def get_release_file(self, version: str, channel: str = None) -> Path:
        """Получить файл Terminal.exe для версии"""
        channel = self._validate_channel(channel)
        terminal_file = self.releases_dir / channel / version / "ManekiTerminal.exe"

        if terminal_file.exists():
            return terminal_file

        return None

    def list_versions(self, channel: str = None) -> list:
        """Получить список всех доступных версий Terminal в канале"""
        channel = self._validate_channel(channel)
        versions = []

        channel_dir = self.releases_dir / channel

        # Найти все папки с версиями
        for version_dir in channel_dir.iterdir():
            if version_dir.is_dir():
                version_json = version_dir / "version.json"
                if version_json.exists():
                    with open(version_json, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        data['channel'] = channel
                        versions.append(data)

        # Сортировать по версии (новые сначала)
        versions.sort(
            key=lambda x: self._parse_version(x["version"]),
            reverse=True
        )

        return versions

    def get_channels_info(self) -> dict:
        """Получить информацию о всех каналах"""
        channels_info = {}

        for channel in self.CHANNELS:
            latest = self.get_latest_release(channel)
            versions = self.list_versions(channel)

            channels_info[channel] = {
                "name": channel,
                "latest_version": latest.get('version') if latest else None,
                "total_versions": len(versions),
                "available": latest is not None
            }

        return channels_info

    def _parse_version(self, version_str: str) -> tuple:
        """Парсинг версии для сравнения (поддержка 1.0.0-beta)"""
        base_version = version_str.split('-')[0]
        try:
            return tuple(int(x) for x in base_version.split('.'))
        except:
            return (0, 0, 0)


release_manager = ReleaseManager(RELEASES_DIR)


@app.route('/api/updates/latest', methods=['GET'])
def get_latest():
    """Получить последнюю версию Terminal"""
    try:
        channel = request.args.get('channel', 'production')
        release = release_manager.get_latest_release(channel)

        if not release:
            return jsonify({
                "success": False,
                "error": f"No releases available in {channel} channel"
            }), 404

        return jsonify({
            "success": True,
            "data": release
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/updates/check', methods=['GET'])
def check_updates():
    """Проверить наличие обновлений Terminal"""
    try:
        current_version = request.args.get('current', '0.0.0')
        channel = request.args.get('channel', 'production')

        latest = release_manager.get_latest_release(channel)

        if not latest:
            return jsonify({
                "success": False,
                "error": f"No releases available in {channel} channel"
            }), 404

        latest_version = latest['version']

        # Сравнить версии
        update_available = _compare_versions(latest_version, current_version) > 0

        response_data = {
            "success": True,
            "data": {
                "update_available": update_available,
                "latest_version": latest_version,
                "current_version": current_version,
                "channel": channel
            }
        }

        # Если обновление доступно (или это первая установка)
        if update_available or current_version == '0.0.0':
            response_data["data"].update({
                "version": latest_version,
                "build": latest.get("build"),
                "release_date": latest.get("release_date"),
                "download_url": latest.get("download_url"),
                "size": latest.get("size"),
                "sha256": latest.get("sha256"),
                "changelog": latest.get("changelog", []),
                "required": latest.get("required", False)
            })

        return jsonify(response_data)
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/updates/download/<version>', methods=['GET'])
def download_update(version: str):
    """Скачать Terminal.exe определенной версии"""
    try:
        channel = request.args.get('channel', 'production')
        terminal_file = release_manager.get_release_file(version, channel)

        if not terminal_file:
            return jsonify({
                "success": False,
                "error": f"Terminal v{version} not found in {channel} channel"
            }), 404

        return send_file(
            terminal_file,
            as_attachment=True,
            download_name=f"ManekiTerminal-{version}.exe"
        )
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/updates/changelog/<version>', methods=['GET'])
def get_changelog(version: str):
    """Получить changelog конкретной версии"""
    try:
        channel = request.args.get('channel', 'production')
        release = release_manager.get_release(version, channel)

        if not release:
            return jsonify({
                "success": False,
                "error": "Release not found"
            }), 404

        return jsonify({
            "success": True,
            "data": {
                "version": version,
                "channel": channel,
                "changelog": release.get('changelog', []),
                "release_date": release.get('release_date')
            }
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/updates/versions', methods=['GET'])
def get_versions():
    """Получить список всех доступных версий Terminal в канале"""
    try:
        channel = request.args.get('channel', 'production')
        versions = release_manager.list_versions(channel)

        return jsonify({
            "success": True,
            "data": {
                "channel": channel,
                "versions": versions,
                "count": len(versions)
            }
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/channels', methods=['GET'])
def get_channels():
    """Получить информацию о всех каналах"""
    try:
        channels_info = release_manager.get_channels_info()

        return jsonify({
            "success": True,
            "data": {
                "channels": channels_info,
                "available_channels": release_manager.CHANNELS,
                "default_channel": release_manager.DEFAULT_CHANNEL
            }
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    channels_info = release_manager.get_channels_info()

    return jsonify({
        "status": "healthy",
        "service": "ManekiTerminal Update Server",
        "version": "4.0",
        "mode": "release_channels",
        "channels": channels_info
    })


def _compare_versions(v1: str, v2: str) -> int:
    """Сравнить версии. Возвращает: 1 если v1 > v2, -1 если v1 < v2, 0 если равны"""
    # Убираем суффиксы для корректного сравнения
    v1_base = v1.split('-')[0]
    v2_base = v2.split('-')[0]

    parts1 = [int(x) for x in v1_base.split('.')]
    parts2 = [int(x) for x in v2_base.split('.')]

    for i in range(max(len(parts1), len(parts2))):
        p1 = parts1[i] if i < len(parts1) else 0
        p2 = parts2[i] if i < len(parts2) else 0

        if p1 > p2:
            return 1
        elif p1 < p2:
            return -1

    return 0


if __name__ == '__main__':
    print("=" * 70)
    print("🚀 ManekiTerminal Update Server v4.0 (Release Channels)")
    print("=" * 70)
    print(f"\n📂 Releases directory: {RELEASES_DIR.absolute()}")
    print("📝 Mode: Release Channels (production/testing)")

    # Проверить каналы
    channels_info = release_manager.get_channels_info()

    for channel_name, info in channels_info.items():
        print(f"\n📦 Channel: {channel_name.upper()}")
        if info['available']:
            print(f"   ✓ Latest version: {info['latest_version']}")
            print(f"   ✓ Total versions: {info['total_versions']}")
        else:
            print(f"   ⚠️  No releases available")

    print("\n" + "=" * 70)
    print("📡 Starting server on http://0.0.0.0:5000")
    print("=" * 70)
    print("\nTerminal Endpoints:")
    print("  GET  /api/updates/latest?channel=production")
    print("  GET  /api/updates/check?current=1.0.0&channel=production")
    print("  GET  /api/updates/download/<version>?channel=production")
    print("  GET  /api/updates/changelog/<version>?channel=production")
    print("  GET  /api/updates/versions?channel=production")
    print("\nChannel Management:")
    print("  GET  /api/channels")
    print("\nOther:")
    print("  GET  /health")
    print("\n💡 Tip: Omit 'channel' parameter to use default (production)")
    print("\n")

    app.run(host='0.0.0.0', port=5000, debug=True)