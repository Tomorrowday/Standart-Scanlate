# tests/api/test_http_flows.py
# Сквозной быстрый HTTP-сценарий на временной БД (ML не вызывается).

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main import app

pytestmark = pytest.mark.api


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n")


@pytest.fixture
def client():
    # TestClient без context manager не запускает lifespan и не грузит ML-веса.
    return TestClient(app)


def _scan_project(client: TestClient, root: Path) -> dict:
    res = client.post("/api/projects/scan", json={"name": "HTTP Test", "folder_path": str(root)})
    assert res.status_code == 200, res.text
    return res.json()


def test_full_http_flow(client, tmp_path):
    root = tmp_path / "manga"
    _touch(root / "cover.png")
    _touch(root / "Chapter 1" / "001.png")
    _touch(root / "Chapter 1" / "002.png")
    _touch(root / "Chapter 2" / "001.png")

    scan = _scan_project(client, root)
    assert scan["success"] is True

    projects = client.get("/api/projects").json()["projects"]
    assert len(projects) == 1
    title_id = projects[0]["id"]

    tree = client.get(f"/api/projects/{title_id}/tree").json()["title"]
    assert [c["chapter_number"] for c in tree["chapters"]] == ["Chapter 1", "Chapter 2"]
    chapter_id = tree["chapters"][0]["id"]
    page_id = tree["chapters"][0]["pages"][0]["id"]

    # Сохранение и чтение баблов.
    block_payload = {
        "blocks": [
            {
                "id": "flow-block-1",
                "class_id": 0,
                "x": 0.1,
                "y": 0.1,
                "width": 0.3,
                "height": 0.2,
                "rotation": 0,
                "jap_text": "こんにちは",
                "rus_text": "Привет",
                "speaker": "Макима",
                "order_index": 1,
                "status": "translated",
            }
        ]
    }
    saved = client.post(f"/api/pages/{page_id}/blocks", json=block_payload)
    assert saved.status_code == 200, saved.text
    assert saved.json()["page_status"] == "translated"

    blocks = client.get(f"/api/pages/{page_id}/blocks").json()["blocks"]
    assert len(blocks) == 1
    assert blocks[0]["rus_text"] == "Привет"

    speakers = client.get(f"/api/pages/{page_id}/speakers").json()["speakers"]
    assert "Макима" in speakers

    # Глоссарий CRUD.
    added = client.post(
        f"/api/projects/{title_id}/glossary",
        json={"jap_word": "東京", "rus_word": "Токио", "context": "город"},
    )
    assert added.status_code == 200
    entry_id = added.json()["item"]["id"]
    glossary = client.get(f"/api/projects/{title_id}/glossary").json()["items"]
    assert any(item["jap_word"] == "東京" for item in glossary)

    # Экспорт диалогов (Content-Disposition с UTF-8/ASCII фоллбэком).
    exported = client.get(f"/api/chapters/{chapter_id}/export-dialogue")
    assert exported.status_code == 200
    assert "attachment" in exported.headers["content-disposition"]
    dialogues = json.loads(exported.text)
    assert dialogues[0]["id"] == "1-1"
    assert dialogues[0]["ru"] == "Привет"

    # Импорт диалогов через multipart.
    import_payload = json.dumps([{"id": "1-1", "ru": "Новый перевод"}], ensure_ascii=False).encode("utf-8")
    imported = client.post(
        f"/api/chapters/{chapter_id}/import-dialogue",
        files={"file": ("dialogues.json", import_payload, "application/json")},
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["updated_count"] == 1

    # Таймер главы.
    started = client.post(f"/api/chapters/{chapter_id}/timer/start")
    assert started.status_code == 200
    assert started.json()["is_running"] is True
    status = client.get(f"/api/chapters/{chapter_id}/timer/status").json()
    assert status["is_running"] is True
    stopped = client.post(f"/api/chapters/{chapter_id}/timer/stop").json()
    assert stopped["is_running"] is False

    # Детальная статистика.
    stats = client.get("/api/projects/all-detailed-stats").json()
    assert stats["success"] is True
    assert stats["projects"][0]["total_pages"] == 3

    # Удаление термина, главы и проекта.
    assert client.delete(f"/api/projects/{title_id}/glossary/{entry_id}").status_code == 200
    assert client.delete(f"/api/chapters/{chapter_id}").status_code == 200
    tree_after = client.get(f"/api/projects/{title_id}/tree").json()["title"]
    assert [c["chapter_number"] for c in tree_after["chapters"]] == ["Chapter 2"]

    assert client.delete(f"/api/projects/{title_id}").status_code == 200
    assert client.get("/api/projects").json()["projects"] == []


def test_http_errors_use_status_codes(client):
    assert client.get("/api/pages/99999").status_code == 404
    assert client.get("/api/pages/99999/blocks").json()["blocks"] == []
    assert client.delete("/api/chapters/99999").status_code == 404
    assert client.get("/api/projects/99999/tree").status_code == 404


def test_global_settings_partial_update_over_http(client):
    res = client.put(
        "/api/projects/global-settings",
        json={"detect_conf": 0.5, "export_format": "webp"},
    )
    assert res.status_code == 200
    settings = res.json()["settings"]
    assert settings["detect_conf"] == pytest.approx(0.5)
    assert settings["export_format"] == "webp"
    # Поля, переданные как None/отсутствующие, остаются прежними.
    assert settings["font_bubble"] == "v_CCFaceFront"
