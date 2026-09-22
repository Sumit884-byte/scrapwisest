from pathlib import Path

from app.services.image_service import ImageService


def test_cleanup_image_removes_temporary_upload(tmp_path: Path):
    image_path = tmp_path / "temporary.jpg"
    image_path.write_bytes(b"test")

    ImageService().cleanup_image(str(image_path))

    assert not image_path.exists()
