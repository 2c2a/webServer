"""
HTML 页面渲染路由

包含错误页面、文档页面、favicon 等
"""
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/404", tags=["pages"])
async def page_404(request: Request):
    """404 错误页面"""
    return templates.TemplateResponse("errors/404.html", {
        "request": request,
    }, status_code=404)


@router.get("/500", tags=["pages"])
async def page_500(request: Request):
    """500 错误页面"""
    return templates.TemplateResponse("errors/500.html", {
        "request": request,
    }, status_code=500)


@router.get("/favicon.ico", tags=["pages"])
async def favicon():
    """Favicon"""
    from pathlib import Path

    favicon_path = Path("static/img/favicon.svg")
    if favicon_path.exists():
        return FileResponse(
            path=str(favicon_path),
            media_type="image/svg+xml",
        )
    return FileResponse(
        path=str(favicon_path),
        media_type="image/svg+xml",
    )


@router.get("/docs", tags=["pages"])
async def docs_page(request: Request):
    """文档页面"""
    return templates.TemplateResponse("docs/index.html", {
        "request": request,
    })
