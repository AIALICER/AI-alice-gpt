"""
キャラクター生成 GUI（tkinter）
"""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

from .generator import GeneratorError, build_spec, fetch_bot_info, generate_character
from .project_patcher import PARTNER_NONE_LABEL, PatchOptions, list_registry_keys


class CharacterCreatorApp(tk.Tk):
    def __init__(self, project_root: Path) -> None:
        super().__init__()
        self.project_root = project_root
        self.title("AI-Alice キャラクター生成")
        self.minsize(720, 680)
        self._build_ui()
        self._refresh_partner_choices()

    def _build_ui(self) -> None:
        pad = {"padx": 12, "pady": 6}
        main = ttk.Frame(self, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            main,
            text="Discord Bot トークン・キャラクター名・system_instruction を入力して生成します。",
            wraplength=680,
        ).pack(anchor=tk.W, **pad)

        token_frame = ttk.LabelFrame(main, text="必須入力", padding=8)
        token_frame.pack(fill=tk.X, **pad)

        ttk.Label(token_frame, text="Discord Bot Token").grid(row=0, column=0, sticky=tk.W)
        self.token_var = tk.StringVar()
        token_entry = ttk.Entry(token_frame, textvariable=self.token_var, show="•", width=72)
        token_entry.grid(row=0, column=1, sticky=tk.EW, padx=(8, 0), pady=4)
        ttk.Button(token_frame, text="トークン確認", command=self._verify_token).grid(
            row=0, column=2, padx=(8, 0)
        )
        token_frame.columnconfigure(1, weight=1)

        char_frame = ttk.LabelFrame(main, text="キャラクター設定（必須）", padding=8)
        char_frame.pack(fill=tk.X, pady=(0, 4))

        ttk.Label(char_frame, text="フォルダ名").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.folder_var = tk.StringVar()
        folder_entry = ttk.Entry(char_frame, textvariable=self.folder_var, width=24)
        folder_entry.grid(row=0, column=1, sticky=tk.W, padx=(8, 0))
        ttk.Label(char_frame, text="→ characters/フォルダ名/").grid(row=0, column=2, sticky=tk.W, padx=(8, 0))

        ttk.Label(char_frame, text="起動スクリプト").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.script_var = tk.StringVar()
        script_entry = ttk.Entry(char_frame, textvariable=self.script_var, width=24)
        script_entry.grid(row=1, column=1, sticky=tk.W, padx=(8, 0))
        ttk.Label(char_frame, text="→ ○○.py（拡張子不要）").grid(row=1, column=2, sticky=tk.W, padx=(8, 0))

        optional_frame = ttk.LabelFrame(main, text="任意（空欄時はトークンから推定）", padding=8)
        optional_frame.pack(fill=tk.X, pady=(0, 4))

        ttk.Label(optional_frame, text="表示名（!コマンド用）").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.display_name_var = tk.StringVar()
        ttk.Entry(optional_frame, textvariable=self.display_name_var, width=32).grid(
            row=0, column=1, sticky=tk.W, padx=(8, 0)
        )

        ttk.Label(optional_frame, text="内部ID（DB用）").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.character_name_var = tk.StringVar()
        ttk.Entry(optional_frame, textvariable=self.character_name_var, width=32).grid(
            row=1, column=1, sticky=tk.W, padx=(8, 0)
        )

        self.bot_info_var = tk.StringVar(value="トークン確認で Bot 情報と名前の候補を表示します")
        ttk.Label(optional_frame, textvariable=self.bot_info_var, wraplength=640).grid(
            row=2, column=0, columnspan=2, sticky=tk.W, pady=(8, 0)
        )

        ttk.Label(main, text="system_instruction").pack(anchor=tk.W, pady=(8, 0))
        self.instruction_text = scrolledtext.ScrolledText(main, height=12, wrap=tk.WORD, font=("Consolas", 10))
        self.instruction_text.pack(fill=tk.BOTH, expand=True, pady=4)
        self.instruction_text.insert(
            "1.0",
            "[ROLE]\nあなたは〇〇というキャラクターです。\n\n[OUTPUT_RULES]\n- 一人称は「私」\n",
        )

        patch_frame = ttk.LabelFrame(main, text="設定ファイルへの追記", padding=8)
        patch_frame.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(
            patch_frame,
            text="✓ .env（新規キーのみ）と bot_id_list（Bot登録）は常に自動追記（既存は上書きしません）",
            wraplength=660,
        ).grid(row=0, column=0, columnspan=3, sticky=tk.W, pady=(0, 6))

        self.auto_partner_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            patch_frame,
            text="PARTNER_MAP（相方Bot）を自動追記",
            variable=self.auto_partner_var,
        ).grid(row=1, column=0, sticky=tk.W)
        ttk.Label(patch_frame, text="相方:").grid(row=1, column=1, sticky=tk.E, padx=(12, 4))
        self.partner_var = tk.StringVar(value=PARTNER_NONE_LABEL)
        self.partner_combo = ttk.Combobox(
            patch_frame,
            textvariable=self.partner_var,
            values=[PARTNER_NONE_LABEL, "alice", "kei", "yuka"],
            width=18,
            state="readonly",
        )
        self.partner_combo.grid(row=1, column=2, sticky=tk.W)

        self.auto_compose_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            patch_frame,
            text="compose.yaml（Docker サービス）を自動追記",
            variable=self.auto_compose_var,
        ).grid(row=2, column=0, columnspan=3, sticky=tk.W, pady=(4, 0))

        self.status_var = tk.StringVar(value="準備完了")
        ttk.Label(main, textvariable=self.status_var, foreground="#444").pack(anchor=tk.W, pady=(8, 0))

        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, pady=(8, 0))
        self.generate_btn = ttk.Button(
            btn_frame, text="キャラクターを生成", command=self._on_generate
        )
        self.generate_btn.pack(side=tk.RIGHT)
        self.clear_btn = ttk.Button(btn_frame, text="クリア", command=self._on_clear)
        self.clear_btn.pack(side=tk.RIGHT, padx=(0, 8))

    def _optional_character_fields(self) -> tuple[str | None, str | None]:
        display = self.display_name_var.get().strip()
        character = self.character_name_var.get().strip()
        return display or None, character or None

    def _verify_token(self) -> None:
        try:
            bot = fetch_bot_info(self.token_var.get())
        except GeneratorError as exc:
            messagebox.showerror("トークン確認", str(exc))
            return
        self.status_var.set(f"Bot 確認 OK: {bot.display_name} (@{bot.username}) ID={bot.bot_id}")
        self.bot_info_var.set(
            f"Bot名: {bot.display_name} / ユーザー名: {bot.username} / ID: {bot.bot_id}"
        )
        from .generator import folder_name_from_username, slug_character_name

        if not self.folder_var.get().strip():
            self.folder_var.set(folder_name_from_username(bot.username))
        if not self.script_var.get().strip():
            self.script_var.set(folder_name_from_username(bot.username))
        if not self.display_name_var.get().strip():
            self.display_name_var.set(bot.display_name)
        if not self.character_name_var.get().strip():
            self.character_name_var.set(slug_character_name(bot.username))

    def _on_clear(self) -> None:
        self.token_var.set("")
        self.folder_var.set("")
        self.script_var.set("")
        self.display_name_var.set("")
        self.character_name_var.set("")
        self.instruction_text.delete("1.0", tk.END)
        self.status_var.set("クリアしました")
        self.bot_info_var.set("トークン確認で Bot 情報と名前の候補を表示します")

    def _on_generate(self) -> None:
        instruction = self.instruction_text.get("1.0", tk.END).strip()
        folder_name = self.folder_var.get()
        script_name = self.script_var.get()
        display_name, character_name = self._optional_character_fields()

        try:
            preview = build_spec(
                discord_token=self.token_var.get(),
                system_instruction=instruction,
                folder_name=folder_name,
                script_name=script_name,
                display_name=display_name,
                character_name=character_name,
            )
        except GeneratorError as exc:
            messagebox.showerror("生成エラー", str(exc))
            return

        patch_opts = self._patch_options()
        auto_lines = [
            "・.env（新規キーのみ）",
            "・bot_id_list.py（BOT_REGISTRY）",
        ]
        if patch_opts.auto_partner_map:
            auto_lines.append(f"・bot_id_list.py（PARTNER_MAP → {patch_opts.partner_name}）")
        else:
            auto_lines.append(
                "・PARTNER_MAP → 手動（未登録時は他 Bot が自動で相方になります）"
            )
        if patch_opts.auto_compose:
            auto_lines.append("・compose.yaml")
        else:
            auto_lines.append("・compose.yaml → 手動（compose.yaml を直接編集）")

        confirm = messagebox.askyesno(
            "生成の確認",
            (
                f"以下のキャラクターを生成します。\n\n"
                f"フォルダ: characters/{preview.folder_name}/\n"
                f"起動: python characters/{preview.folder_name}/{preview.script_name}.py\n"
                f"表示名: {preview.display_name}\n"
                f"内部ID: {preview.character_name}\n"
                f"環境変数: {preview.discord_token_env}\n"
                f"Bot ID: {preview.bot_id}\n\n"
                "追記:\n"
                + "\n".join(auto_lines)
            ),
        )
        if not confirm:
            return

        self._set_generating(True)
        self.status_var.set("生成中...（messages.py を Gemini で生成しています・最大約2分）")
        self.update_idletasks()

        def worker() -> None:
            try:
                result = generate_character(
                    project_root=self.project_root,
                    discord_token=self.token_var.get(),
                    system_instruction=instruction,
                    folder_name=folder_name,
                    script_name=script_name,
                    display_name=display_name,
                    character_name=character_name,
                    patch_options=patch_opts,
                )
            except GeneratorError as exc:
                self.after(0, lambda: self._on_generate_failed(str(exc)))
                return
            except Exception as exc:
                self.after(0, lambda: self._on_generate_failed(f"予期しないエラー: {exc}"))
                return
            self.after(0, lambda: self._on_generate_success(result, patch_opts))

        threading.Thread(target=worker, daemon=True).start()

    def _set_generating(self, active: bool) -> None:
        state = tk.DISABLED if active else tk.NORMAL
        self.generate_btn.configure(state=state)
        self.clear_btn.configure(state=state)

    def _on_generate_failed(self, message: str) -> None:
        self._set_generating(False)
        messagebox.showerror("生成エラー", message)
        self.status_var.set("生成に失敗しました")

    def _on_generate_success(self, result, patch_opts: PatchOptions) -> None:
        self._set_generating(False)
        spec = result.spec
        manual_note = ""
        if not patch_opts.auto_partner_map or not patch_opts.auto_compose:
            manual_note = (
                "\nチェックを外した項目は bot_id_list.py / compose.yaml を手動で編集してください。"
            )

        patch_note = result.patch_summary
        if patch_note:
            patch_note = f"\n\n【追記結果】\n{patch_note}"

        if result.messages_error:
            messagebox.showwarning(
                "messages.py（Gemini）",
                result.messages_error,
            )

        messagebox.showinfo(
            "生成完了",
            (
                f"characters/{spec.folder_name}/ を作成しました。"
                f"{patch_note}{manual_note}\n\n"
                f"起動: python characters/{spec.folder_name}/{spec.script_name}.py"
            ),
        )
        self.status_var.set(f"完了: characters/{spec.folder_name}/")

    def _patch_options(self) -> PatchOptions:
        return PatchOptions(
            auto_partner_map=self.auto_partner_var.get(),
            partner_name=self.partner_var.get().strip() or "alice",
            auto_compose=self.auto_compose_var.get(),
        )

    def _refresh_partner_choices(self) -> None:
        registry_path = self.project_root / "characters" / "bot_id_list.py"
        if registry_path.exists():
            keys = list_registry_keys(registry_path.read_text(encoding="utf-8"))
            values = [PARTNER_NONE_LABEL, *keys]
            self.partner_combo["values"] = values
            if self.partner_var.get() not in values:
                self.partner_var.set(PARTNER_NONE_LABEL)


def run_app(project_root: Path | None = None) -> None:
    root = project_root or Path(__file__).resolve().parents[2]
    app = CharacterCreatorApp(project_root=root)
    app.mainloop()

