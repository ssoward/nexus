from fastapi import APIRouter, Depends, HTTPException, status
from typing import List

from app.database import db
from app.dependencies import get_current_user
from app.models.page import Page, PageCreate, PageUpdate

router = APIRouter(prefix="/api/pages", tags=["pages"])


@router.get("", response_model=List[Page])
async def list_pages(current_user: dict = Depends(get_current_user)):
    rows = await db.fetchall(
        "SELECT * FROM pages WHERE user_id = ? ORDER BY position, id",
        (current_user["id"],),
    )
    return rows


@router.post("", response_model=Page, status_code=status.HTTP_201_CREATED)
async def create_page(req: PageCreate, current_user: dict = Depends(get_current_user)):
    pid = await db.execute_returning(
        "INSERT INTO pages (user_id, name, url) VALUES (?, ?, ?)",
        (current_user["id"], req.name, req.url),
    )
    row = await db.fetchone("SELECT * FROM pages WHERE id = ?", (pid,))
    return row


@router.patch("/{page_id}", response_model=Page)
async def update_page(
    page_id: int,
    req: PageUpdate,
    current_user: dict = Depends(get_current_user),
):
    existing = await db.fetchone(
        "SELECT * FROM pages WHERE id = ? AND user_id = ?",
        (page_id, current_user["id"]),
    )
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")

    updates = []
    params = []
    if req.name is not None:
        updates.append("name = ?")
        params.append(req.name)
    if req.url is not None:
        updates.append("url = ?")
        params.append(req.url)
    if req.position is not None:
        updates.append("position = ?")
        params.append(req.position)

    if updates:
        params.append(page_id)
        await db.execute(f"UPDATE pages SET {', '.join(updates)} WHERE id = ?", tuple(params))

    row = await db.fetchone("SELECT * FROM pages WHERE id = ?", (page_id,))
    return row


@router.delete("/{page_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_page(page_id: int, current_user: dict = Depends(get_current_user)):
    existing = await db.fetchone(
        "SELECT * FROM pages WHERE id = ? AND user_id = ?",
        (page_id, current_user["id"]),
    )
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")
    await db.execute("DELETE FROM pages WHERE id = ?", (page_id,))
