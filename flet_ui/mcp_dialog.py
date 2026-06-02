"""MCP server management dialog."""

import flet as ft


STATUS_LABELS = {
    "pending": ("等待中", "#94A3B8"),
    "connecting": ("连接中", "#F59E0B"),
    "connected": ("已连接", "#10B981"),
    "failed": ("连接失败", "#EF4444"),
    "disconnected": ("已断开", "#94A3B8"),
}


def show_mcp_dialog(page: ft.Page, controller):
    """Open the MCP management dialog."""

    if not controller or not controller.mcp_manager:
        dlg = ft.AlertDialog(
            title=ft.Text("MCP 管理", size=16, weight=ft.FontWeight.W_600),
            content=ft.Text("无 MCP 服务器配置", size=13, color="#64748B"),
            actions=[ft.TextButton(content=ft.Text("关闭", size=13),
                     on_click=lambda e: page.pop_dialog())],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=10),
        )
        page.show_dialog(dlg)
        return

    mgr = controller.mcp_manager
    statuses = mgr.get_all_statuses()

    # Build server cards
    server_cards = []

    for name, info in statuses.items():
        status_label, status_color = STATUS_LABELS.get(
            info["status"], ("未知", "#94A3B8"))

        # Status badge
        status_badge = ft.Container(
            content=ft.Text(status_label, size=10, color=status_color,
                          weight=ft.FontWeight.W_600),
            padding=ft.Padding.symmetric(horizontal=8, vertical=2),
            border_radius=6,
            bgcolor=status_color + "15",
            border=ft.Border.all(1, status_color + "30"),
        )

        # Server header row
        header = ft.Row([
            ft.Text(name, size=13, weight=ft.FontWeight.W_600, color="#1E1B3A"),
            status_badge,
        ], spacing=10)

        # Tool count
        tool_text = ft.Text(
            f"{info['tool_count']} 个工具", size=11, color="#64748B")

        # Expandable tool list
        tool_items = []
        for t in info.get("tools", []):
            tool_items.append(
                ft.Container(
                    content=ft.Column([
                        ft.Text(t["name"], size=11, weight=ft.FontWeight.W_600,
                              color="#475569"),
                        ft.Text(t.get("description", ""), size=10, color="#94A3B8"),
                    ], spacing=1, tight=True),
                    padding=ft.Padding.only(left=16, top=4, bottom=4),
                )
            )

        expanded = False

        def make_toggle(idx):
            def toggle(e):
                nonlocal expanded
                expanded = not expanded
                tool_col.visible = expanded
                toggle_btn.text = "▾" if expanded else "▸"
                toggle_btn.update()
                tool_col.update()
            return toggle

        toggle_btn = ft.TextButton(
            content=ft.Text("▸", size=11, color="#64748B"),
            style=ft.ButtonStyle(padding=ft.Padding.all(2)),
        )
        toggle_btn.on_click = make_toggle(0)

        tool_col = ft.Column(tool_items, spacing=0, visible=False)

        expand_row = ft.Row([
            toggle_btn, tool_text,
        ], spacing=4)

        # Stop / Restart buttons
        def make_stop(n):
            async def stop(e):
                await mgr.stop_server(n)
                _refresh(page, controller)
            return stop

        def make_restart(n):
            async def restart(e):
                await mgr.restart_server(n)
                _refresh(page, controller)
            return restart

        stop_btn = ft.TextButton(
            content=ft.Text("停止", size=10, color="#EF4444"),
            style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=8, vertical=2)),
            on_click=make_stop(name),
        )
        restart_btn = ft.TextButton(
            content=ft.Text("重连", size=10, color="#6366F1"),
            style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=8, vertical=2)),
            on_click=make_restart(name),
        )

        card = ft.Container(
            content=ft.Column([
                header,
                expand_row,
                tool_col,
                ft.Row([stop_btn, restart_btn], spacing=4),
            ], spacing=4, tight=True),
            padding=ft.Padding.all(12),
            border=ft.Border.all(1, "#EEF0F4"),
            border_radius=8,
            bgcolor="#FAFBFC",
        )
        server_cards.append(card)

    if not server_cards:
        server_cards.append(
            ft.Text("无 MCP 服务器", size=13, color="#94A3B8"))

    content_col = ft.Column(
        server_cards, spacing=10, scroll=ft.ScrollMode.AUTO)
    content_container = ft.Container(
        content=content_col, width=500, height=400)

    def refresh(e=None):
        page.pop_dialog()
        show_mcp_dialog(page, controller)

    dlg = ft.AlertDialog(
        title=ft.Text("MCP 管理", size=16, weight=ft.FontWeight.W_600),
        content=content_container,
        actions=[
            ft.TextButton(
                content=ft.Text("刷新", size=13, color="#6366F1"),
                on_click=refresh,
            ),
            ft.TextButton(
                content=ft.Text("关闭", size=13, color="#64748B"),
                on_click=lambda e: page.pop_dialog(),
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
        shape=ft.RoundedRectangleBorder(radius=10),
    )
    page.show_dialog(dlg)


def _refresh(page, controller):
    page.pop_dialog()
    show_mcp_dialog(page, controller)
