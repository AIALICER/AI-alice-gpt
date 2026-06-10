"""
Bot 設定管理 GUI（messages.py / 特殊コマンド / スラッシュコマンド）
"""

from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from .paths import get_project_root
from .scanner import (
    BotManagerError,
    CharacterInfo,
    discover_characters,
    extract_help_mentions,
    load_messages,
    load_system_instruction,
    save_messages,
    save_special_commands,
    validate_messages,
)
from .slash_catalog import (
    SlashCommandInfo,
    commands_for_character,
    compare_help_vs_implemented,
    parse_slash_commands,
)


class BotManagerApp(tk.Tk):
    def __init__(self, project_root: Path) -> None:
        super().__init__()
        self.project_root = project_root
        self.title("AI-Alice Bot 設定マネージャ")
        self.minsize(960, 720)
        self.geometry("1100x780")

        self.characters: list[CharacterInfo] = []
        self.slash_commands: list[SlashCommandInfo] = []
        self.current: CharacterInfo | None = None
        self._special_cmds: dict[str, dict[str, str]] = {}

        self._build_ui()
        self._reload_catalog()

    def _build_ui(self) -> None:
        main = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        left = ttk.Frame(main, padding=4)
        main.add(left, weight=1)

        ttk.Label(left, text="キャラクター").pack(anchor=tk.W)
        self.char_list = tk.Listbox(left, width=28, exportselection=False)
        self.char_list.pack(fill=tk.BOTH, expand=True, pady=4)
        self.char_list.bind("<<ListboxSelect>>", self._on_select_character)

        ttk.Button(left, text="再読み込み", command=self._reload_catalog).pack(fill=tk.X, pady=2)

        right = ttk.Frame(main, padding=4)
        main.add(right, weight=4)

        self.notebook = ttk.Notebook(right)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self._build_overview_tab()
        self._build_messages_tab()
        self._build_special_tab()
        self._build_slash_tab()

        self.status_var = tk.StringVar(value="準備完了")
        ttk.Label(right, textvariable=self.status_var).pack(anchor=tk.W, pady=(6, 0))

    def _build_overview_tab(self) -> None:
        frame = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(frame, text="概要")

        self.overview_text = scrolledtext.ScrolledText(frame, height=24, wrap=tk.WORD, font=("Consolas", 10))
        self.overview_text.pack(fill=tk.BOTH, expand=True)

    def _build_messages_tab(self) -> None:
        frame = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(frame, text="messages.py")

        toolbar = ttk.Frame(frame)
        toolbar.pack(fill=tk.X, pady=(0, 6))
        ttk.Button(toolbar, text="検証", command=self._validate_messages).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="保存", command=self._save_messages).pack(side=tk.LEFT, padx=6)
        ttk.Button(toolbar, text="元に戻す", command=self._reload_messages).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="Geminiで再生成", command=self._generate_messages).pack(
            side=tk.LEFT, padx=(12, 0)
        )

        self.messages_editor = scrolledtext.ScrolledText(frame, wrap=tk.NONE, font=("Consolas", 10))
        self.messages_editor.pack(fill=tk.BOTH, expand=True)

        self.messages_result = scrolledtext.ScrolledText(
            frame, height=6, wrap=tk.WORD, font=("Consolas", 9), state=tk.DISABLED
        )
        self.messages_result.pack(fill=tk.X, pady=(6, 0))

    def _build_special_tab(self) -> None:
        frame = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(frame, text="特殊コマンド")

        toolbar = ttk.Frame(frame)
        toolbar.pack(fill=tk.X, pady=(0, 6))
        ttk.Button(toolbar, text="追加", command=self._add_special).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="編集", command=self._edit_special).pack(side=tk.LEFT, padx=4)
        ttk.Button(toolbar, text="削除", command=self._delete_special).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="保存", command=self._save_special).pack(side=tk.RIGHT)

        cols = ("command", "message", "file")
        self.special_tree = ttk.Treeview(frame, columns=cols, show="headings", height=12)
        self.special_tree.heading("command", text="コマンド")
        self.special_tree.heading("message", text="メッセージ")
        self.special_tree.heading("file", text="添付ファイル")
        self.special_tree.column("command", width=120)
        self.special_tree.column("message", width=360)
        self.special_tree.column("file", width=280)
        self.special_tree.pack(fill=tk.BOTH, expand=True)

        hint = (
            "テキスト完全一致で発火します（例: !光よ!）。\n"
            "message: 送信テキスト / file: 画像等のパス（プロジェクトルート相対）"
        )
        ttk.Label(frame, text=hint, wraplength=800).pack(anchor=tk.W, pady=(6, 0))

    def _build_slash_tab(self) -> None:
        frame = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(frame, text="スラッシュコマンド")

        ttk.Label(
            frame,
            text="common/bot_base.py から解析した登録コマンドと、MSG_HELP 記載の整合性",
            wraplength=800,
        ).pack(anchor=tk.W, pady=(0, 6))

        cols = ("name", "scope", "description", "status")
        self.slash_tree = ttk.Treeview(frame, columns=cols, show="headings", height=14)
        for col, title, width in [
            ("name", "コマンド", 140),
            ("scope", "対象", 80),
            ("description", "説明", 360),
            ("status", "整合性", 120),
        ]:
            self.slash_tree.heading(col, text=title)
            self.slash_tree.column(col, width=width)
        self.slash_tree.pack(fill=tk.BOTH, expand=True)

        self.slash_summary = scrolledtext.ScrolledText(
            frame, height=8, wrap=tk.WORD, font=("Consolas", 9), state=tk.DISABLED
        )
        self.slash_summary.pack(fill=tk.X, pady=(6, 0))

    def _reload_catalog(self) -> None:
        try:
            self.characters = discover_characters(self.project_root)
            bot_base = self.project_root / "common" / "bot_base.py"
            self.slash_commands = parse_slash_commands(bot_base) if bot_base.exists() else []
        except BotManagerError as exc:
            messagebox.showerror("読み込みエラー", str(exc))
            return

        self.char_list.delete(0, tk.END)
        for ch in self.characters:
            self.char_list.insert(tk.END, f"{ch.display_name} ({ch.folder_name})")

        self.status_var.set(f"{len(self.characters)} キャラ / スラッシュ {len(self.slash_commands)} 件を読み込み")
        if self.characters:
            self.char_list.selection_set(0)
            self._on_select_character()

    def _on_select_character(self, _event=None) -> None:
        sel = self.char_list.curselection()
        if not sel:
            return
        self.current = self.characters[sel[0]]
        self._special_cmds = dict(self.current.special_commands)
        self._refresh_all_panels()

    def _refresh_all_panels(self) -> None:
        if not self.current:
            return
        self._refresh_overview()
        self._reload_messages()
        self._refresh_special_tree()
        self._refresh_slash_panel()

    def _refresh_overview(self) -> None:
        ch = self.current
        if not ch:
            return
        available = commands_for_character(ch.character_name, self.slash_commands)
        lines = [
            f"フォルダ: characters/{ch.folder_name}/",
            f"内部ID: {ch.character_name}",
            f"表示名: {ch.display_name}",
            f"テキストコマンド正規表現: {ch.command_pattern}",
            f"履歴消去: {ch.history_clear_command}",
            f"config: {ch.config_path.relative_to(self.project_root)}",
            f"messages: {ch.messages_path.relative_to(self.project_root) if ch.messages_path.exists() else '（なし）'}",
            f"system_instruction: {ch.system_instruction_path.relative_to(self.project_root) if ch.system_instruction_path.exists() else '（なし）'}",
            "",
            f"特殊コマンド: {len(ch.special_commands)} 件",
            f"利用可能スラッシュ: {len(available)} 件",
        ]
        for cmd in ch.special_commands:
            lines.append(f"  - {cmd}")

        self.overview_text.delete("1.0", tk.END)
        self.overview_text.insert("1.0", "\n".join(lines))

    def _reload_messages(self) -> None:
        if not self.current or not self.current.messages_path.exists():
            self.messages_editor.delete("1.0", tk.END)
            return
        try:
            content = load_messages(self.current.messages_path)
        except BotManagerError as exc:
            messagebox.showerror("エラー", str(exc))
            return
        self.messages_editor.delete("1.0", tk.END)
        self.messages_editor.insert("1.0", content)
        self._set_result(self.messages_result, "")

    def _generate_messages(self) -> None:
        if not self.current:
            return
        ch = self.current
        try:
            instruction = load_system_instruction(ch.system_instruction_path)
        except BotManagerError as exc:
            messagebox.showerror("エラー", str(exc))
            return

        if not messagebox.askyesno(
            "Gemini で再生成",
            (
                f"{ch.display_name} の messages.py を、"
                "system_instruction.txt の内容をもとに Gemini で生成します。\n"
                "エディタの内容は上書きされます（保存するまでファイルは変わりません）。\n\n"
                "続行しますか？"
            ),
        ):
            return

        from tools.character_creator.generator import CharacterSpec
        from tools.character_creator.messages_generator import generate_messages_from_instruction

        fallback_spec = CharacterSpec(
            character_name=ch.character_name,
            display_name=ch.display_name,
            folder_name=ch.folder_name,
            script_name="",
            discord_token_env="",
            bot_id=0,
            bot_display_name=ch.display_name,
            system_instruction=instruction,
            discord_token="",
        )

        self.status_var.set("Gemini で messages.py を生成中…")
        self.update_idletasks()

        result = generate_messages_from_instruction(
            self.project_root,
            display_name=ch.display_name,
            character_name=ch.character_name,
            system_instruction=instruction,
            bot_display_name=ch.display_name,
            template_fallback_spec=fallback_spec,
        )

        if not result.code:
            self.status_var.set("生成に失敗しました")
            messagebox.showerror("Gemini", result.error or "生成に失敗しました。")
            return

        self.messages_editor.delete("1.0", tk.END)
        self.messages_editor.insert("1.0", result.code)

        if result.source == "gemini":
            self.status_var.set("Gemini で生成しました（未保存）")
            self._set_result(self.messages_result, "Gemini 生成完了。内容を確認して「保存」してください。")
            messagebox.showinfo(
                "生成完了",
                "messages.py を Gemini で生成しました。\n内容を確認して「保存」してください。",
            )
        else:
            self.status_var.set("テンプレートで生成しました（未保存）")
            self._set_result(
                self.messages_result,
                result.error or "テンプレートで生成しました。",
            )
            messagebox.showwarning(
                "Gemini 失敗",
                (result.error or "Gemini に失敗したためテンプレートを表示しました。")
                + "\n\n内容を確認して「保存」するか、.env の GEN_API_KEY を確認してください。",
            )

    def _validate_messages(self) -> None:
        if not self.current:
            return
        content = self.messages_editor.get("1.0", tk.END)
        errors, warnings = validate_messages(content)
        lines: list[str] = []
        if errors:
            lines.append("【エラー】")
            lines.extend(f"  - {e}" for e in errors)
        if warnings:
            lines.append("【警告】")
            lines.extend(f"  - {w}" for w in warnings)
        if not lines:
            lines.append("検証 OK")
        self._set_result(self.messages_result, "\n".join(lines))

    def _save_messages(self) -> None:
        if not self.current:
            return
        content = self.messages_editor.get("1.0", tk.END)
        errors, _ = validate_messages(content)
        if errors:
            if not messagebox.askyesno(
                "保存の確認",
                "エラーがありますが保存しますか？\n" + "\n".join(errors[:5]),
            ):
                return
        try:
            save_messages(self.current.messages_path, content)
        except BotManagerError as exc:
            messagebox.showerror("保存エラー", str(exc))
            return
        self.status_var.set(f"保存しました: {self.current.messages_path.name}")
        messagebox.showinfo("保存", "messages.py を保存しました（.bak バックアップあり）。")

    def _refresh_special_tree(self) -> None:
        for item in self.special_tree.get_children():
            self.special_tree.delete(item)
        for cmd, cfg in self._special_cmds.items():
            self.special_tree.insert(
                "",
                tk.END,
                values=(cmd, cfg.get("message", ""), cfg.get("file", "")),
            )

    def _add_special(self) -> None:
        self._open_special_dialog()

    def _edit_special(self) -> None:
        sel = self.special_tree.selection()
        if not sel:
            messagebox.showinfo("編集", "行を選択してください。")
            return
        values = self.special_tree.item(sel[0], "values")
        self._open_special_dialog(command=values[0], message=values[1], file=values[2])

    def _delete_special(self) -> None:
        sel = self.special_tree.selection()
        if not sel:
            return
        cmd = self.special_tree.item(sel[0], "values")[0]
        if messagebox.askyesno("削除", f"「{cmd}」を削除しますか？"):
            self._special_cmds.pop(cmd, None)
            self._refresh_special_tree()

    def _open_special_dialog(
        self,
        command: str = "",
        message: str = "",
        file: str = "",
    ) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("特殊コマンド")
        dialog.transient(self)
        dialog.grab_set()

        ttk.Label(dialog, text="コマンド（完全一致）").grid(row=0, column=0, sticky=tk.W, padx=8, pady=4)
        cmd_var = tk.StringVar(value=command)
        ttk.Entry(dialog, textvariable=cmd_var, width=48).grid(row=0, column=1, padx=8, pady=4)

        ttk.Label(dialog, text="メッセージ").grid(row=1, column=0, sticky=tk.NW, padx=8, pady=4)
        msg_text = scrolledtext.ScrolledText(dialog, width=50, height=4, font=("Consolas", 10))
        msg_text.grid(row=1, column=1, padx=8, pady=4)
        msg_text.insert("1.0", message)

        ttk.Label(dialog, text="ファイルパス").grid(row=2, column=0, sticky=tk.W, padx=8, pady=4)
        file_var = tk.StringVar(value=file)
        file_entry = ttk.Entry(dialog, textvariable=file_var, width=40)
        file_entry.grid(row=2, column=1, sticky=tk.EW, padx=8, pady=4)

        def browse() -> None:
            path = filedialog.askopenfilename(initialdir=str(self.project_root))
            if path:
                try:
                    rel = Path(path).relative_to(self.project_root)
                    file_var.set(str(rel).replace("\\", "/"))
                except ValueError:
                    file_var.set(path)

        ttk.Button(dialog, text="参照...", command=browse).grid(row=2, column=2, padx=4)

        def on_ok() -> None:
            new_cmd = cmd_var.get().strip()
            if not new_cmd:
                messagebox.showerror("エラー", "コマンドを入力してください。", parent=dialog)
                return
            cfg: dict[str, str] = {}
            msg = msg_text.get("1.0", tk.END).strip()
            fpath = file_var.get().strip()
            if msg:
                cfg["message"] = msg
            if fpath:
                cfg["file"] = fpath.replace("\\", "/")
            if not cfg:
                messagebox.showerror("エラー", "メッセージかファイルのどちらかが必要です。", parent=dialog)
                return
            if command and command != new_cmd:
                self._special_cmds.pop(command, None)
            self._special_cmds[new_cmd] = cfg
            self._refresh_special_tree()
            dialog.destroy()

        btn_frame = ttk.Frame(dialog)
        btn_frame.grid(row=3, column=0, columnspan=3, pady=8)
        ttk.Button(btn_frame, text="OK", command=on_ok).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="キャンセル", command=dialog.destroy).pack(side=tk.LEFT)

    def _save_special(self) -> None:
        if not self.current:
            return
        try:
            save_special_commands(self.current.config_path, self._special_cmds)
            self.current.special_commands = dict(self._special_cmds)
        except BotManagerError as exc:
            messagebox.showerror("保存エラー", str(exc))
            return
        self.status_var.set("特殊コマンドを保存しました")
        messagebox.showinfo("保存", "config.py の SPECIAL_COMMANDS を更新しました（.bak あり）。")

    def _refresh_slash_panel(self) -> None:
        if not self.current:
            return
        ch = self.current
        available = commands_for_character(ch.character_name, self.slash_commands)
        help_mentions: set[str] = set()
        if ch.messages_path.exists():
            try:
                help_mentions = extract_help_mentions(load_messages(ch.messages_path))
            except BotManagerError:
                pass

        help_only, not_in_help = compare_help_vs_implemented(help_mentions, available)
        available_names = {c.name for c in available}

        for item in self.slash_tree.get_children():
            self.slash_tree.delete(item)

        for cmd in self.slash_commands:
            if cmd.scope == "alice" and ch.character_name.lower() != "alice":
                status = "—（非対象）"
                tags = ("muted",)
            elif cmd.name in available_names:
                if cmd.name in help_mentions:
                    status = "OK"
                    tags = ("ok",)
                else:
                    status = "HELP未記載"
                    tags = ("warn",)
            else:
                status = "—"
                tags = ("muted",)

            self.slash_tree.insert(
                "",
                tk.END,
                values=(f"/{cmd.name}", cmd.scope, cmd.description, status),
                tags=tags,
            )

        self.slash_tree.tag_configure("ok", foreground="#1a7f37")
        self.slash_tree.tag_configure("warn", foreground="#9a6700")
        self.slash_tree.tag_configure("muted", foreground="#888888")

        summary_lines = [
            f"【{ch.display_name}】利用可能: {', '.join(f'/{c.name}' for c in available) or 'なし'}",
            "",
        ]
        if help_only:
            summary_lines.append("⚠ MSG_HELP にあるが bot_base 未登録（要確認）:")
            summary_lines.extend(f"    /{n}" for n in help_only)
            summary_lines.append("")
        if not_in_help:
            summary_lines.append("ℹ 実装済みだが MSG_HELP に未記載:")
            summary_lines.extend(f"    /{n}" for n in not_in_help)

        self._set_result(self.slash_summary, "\n".join(summary_lines) if summary_lines else "整合性 OK")

    def _set_result(self, widget: scrolledtext.ScrolledText, text: str) -> None:
        widget.configure(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert("1.0", text)
        widget.configure(state=tk.DISABLED)


def run_app(project_root: Path | None = None) -> None:
    root = project_root or get_project_root()
    app = BotManagerApp(project_root=root)
    app.mainloop()
