from fastapi import APIRouter, Depends, HTTPException, status
from typing import List

from app.database import db
from app.dependencies import get_current_user
from app.models.workspace import Workspace, WorkspaceCreate, WorkspaceUpdate

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


@router.get("", response_model=List[Workspace])
async def list_workspaces(current_user: dict = Depends(get_current_user)):
    rows = await db.fetchall(
        "SELECT * FROM workspaces WHERE user_id = ? ORDER BY sort_order, id",
        (current_user["id"],),
    )
    return rows


@router.post("", response_model=Workspace, status_code=status.HTTP_201_CREATED)
async def create_workspace(req: WorkspaceCreate, current_user: dict = Depends(get_current_user)):
    wid = await db.execute_returning(
        "INSERT INTO workspaces (user_id, name, color) VALUES (?, ?, ?)",
        (current_user["id"], req.name, req.color),
    )
    row = await db.fetchone("SELECT * FROM workspaces WHERE id = ?", (wid,))
    return row


@router.patch("/{workspace_id}", response_model=Workspace)
async def update_workspace(
    workspace_id: int,
    req: WorkspaceUpdate,
    current_user: dict = Depends(get_current_user),
):
    existing = await db.fetchone(
        "SELECT * FROM workspaces WHERE id = ? AND user_id = ?",
        (workspace_id, current_user["id"]),
    )
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    updates = []
    params = []
    if req.name is not None:
        updates.append("name = ?")
        params.append(req.name)
    if req.color is not None:
        updates.append("color = ?")
        params.append(req.color)
    if req.sort_order is not None:
        updates.append("sort_order = ?")
        params.append(req.sort_order)

    if updates:
        params.append(workspace_id)
        await db.execute(f"UPDATE workspaces SET {', '.join(updates)} WHERE id = ?", tuple(params))

    row = await db.fetchone("SELECT * FROM workspaces WHERE id = ?", (workspace_id,))
    return row


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(workspace_id: int, current_user: dict = Depends(get_current_user)):
    existing = await db.fetchone(
        "SELECT * FROM workspaces WHERE id = ? AND user_id = ?",
        (workspace_id, current_user["id"]),
    )
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    await db.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))
