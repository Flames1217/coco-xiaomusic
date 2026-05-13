import uvicorn

from coco_xiaomusic.settings import settings
from coco_xiaomusic.web import app


def main():
    uvicorn.run(
        app,
        host=settings.admin_host,
        port=settings.admin_port,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
