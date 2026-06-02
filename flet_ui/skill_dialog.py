"""Skill management dialog."""

import flet as ft
from skills.loader import load_skills


def show_skill_dialog(page: ft.Page, cwd: str | None = None):
    """Open the skill management dialog."""

    skills = load_skills(cwd)

    if not skills:
        dlg = ft.AlertDialog(
            title=ft.Text("技能管理", size=16, weight=ft.FontWeight.W_600),
            content=ft.Text("无可用技能", size=13, color="#64748B"),
            actions=[ft.TextButton(content=ft.Text("关闭", size=13),
                     on_click=lambda e: page.pop_dialog())],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=10),
        )
        page.show_dialog(dlg)
        return

    cards = []
    for s in skills:
        cards.append(
            ft.Container(
                content=ft.Column([
                    ft.Text(s.name, size=13, weight=ft.FontWeight.W_600,
                          color="#1E1B3A"),
                    ft.Text(s.description, size=11, color="#64748B"),
                ], spacing=2, tight=True),
                padding=ft.Padding.all(12),
                border=ft.Border.all(1, "#EEF0F4"),
                border_radius=8,
                bgcolor="#FAFBFC",
            )
        )

    content = ft.Column(cards, spacing=8, scroll=ft.ScrollMode.AUTO)

    dlg = ft.AlertDialog(
        title=ft.Text(f"技能管理 ({len(skills)})", size=16,
                     weight=ft.FontWeight.W_600),
        content=ft.Container(content=content, width=450, height=400),
        actions=[
            ft.TextButton(
                content=ft.Text("关闭", size=13, color="#64748B"),
                on_click=lambda e: page.pop_dialog(),
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
        shape=ft.RoundedRectangleBorder(radius=10),
    )
    page.show_dialog(dlg)
