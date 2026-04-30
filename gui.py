from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk

from main import DEFAULT_CACHE_TTL_SECONDS, RatesError, convert, fetch_rates


COLORS = {
    # Dark-blue main background ("menu")
    "bg": "#071a33",
    "panel": "#071a33",
    "text": "#e7eefc",
    "muted": "#9aa7c0",
    "entry_bg": "#0b1224",
    "glow": "#2aa8ff",
    "glow_dim": "#156ea8",
    "button": "#0a0e16",  # ~2 tones darker than bg/panel
    "button_hover": "#0e1422",
    "button_text": "#e7eefc",
    "shadow": "#000000",
}


class GlowWrap(tk.Frame):
    def __init__(self, parent: tk.Widget, *, glow_color: str, dim_color: str, pad: int = 2) -> None:
        super().__init__(parent, bg=dim_color, highlightthickness=0, bd=0)
        self._glow = glow_color
        self._dim = dim_color
        self._pad = pad

    def wrap(self, widget: tk.Widget) -> tk.Widget:
        widget.pack(in_=self, fill="both", expand=True, padx=self._pad, pady=self._pad)
        widget.bind("<FocusIn>", lambda _e: self.configure(bg=self._glow), add=True)
        widget.bind("<FocusOut>", lambda _e: self.configure(bg=self._dim), add=True)
        return widget


def _rounded_rect_points(x1: int, y1: int, x2: int, y2: int, r: int) -> list[int]:
    r = max(0, min(r, (x2 - x1) // 2, (y2 - y1) // 2))
    return [
        x1 + r,
        y1,
        x2 - r,
        y1,
        x2,
        y1,
        x2,
        y1 + r,
        x2,
        y2 - r,
        x2,
        y2,
        x2 - r,
        y2,
        x1 + r,
        y2,
        x1,
        y2,
        x1,
        y2 - r,
        x1,
        y1 + r,
        x1,
        y1,
    ]


class ShadowButton(tk.Canvas):
    def __init__(
        self,
        parent: tk.Widget,
        *,
        text: str,
        command,
        bg: str,
        fg: str,
        hover_bg: str,
        shadow_color: str,
        shadow_offset: int = 4,
        height: int = 52,
        width: int | None = None,
    ) -> None:
        super().__init__(
            parent,
            bg=parent.cget("bg"),
            height=height,
            width=(width or 1),
            highlightthickness=0,
            bd=0,
        )
        self._command = command
        self._bg = bg
        self._hover_bg = hover_bg
        self._fg = fg
        self._shadow_offset = shadow_offset
        self._height = height
        self._width = width
        self._radius = 14
        self._pressed = False
        self._disabled = False
        self._text = text

        self._shadow_color = shadow_color
        self._font = ("Segoe UI", 11, "bold")

        self._shadow_id = None
        self._rect_id = None
        self._text_id = None

        self.bind("<Configure>", lambda _e: self._redraw(), add=True)
        self.bind("<Enter>", lambda _e: self._on_hover(True), add=True)
        self.bind("<Leave>", lambda _e: self._on_hover(False), add=True)
        self.bind("<ButtonPress-1>", self._press, add=True)
        self.bind("<ButtonRelease-1>", self._release, add=True)
        self.configure(cursor="hand2")
        self._redraw()

    def configure(self, cnf=None, **kw):  # type: ignore[override]
        if kw.get("state") is not None:
            self._disabled = (kw["state"] == "disabled")
            if self._disabled:
                self.configure(cursor="")
            else:
                self.configure(cursor="hand2")
            self._redraw()
        return super().configure(cnf or {}, **{k: v for k, v in kw.items() if k != "state"})

    def _on_click(self) -> None:
        if not self._disabled:
            self._command()

    def _on_hover(self, on: bool) -> None:
        if self._disabled:
            return
        self._hovering = on
        self._redraw()

    def _press(self, _e) -> None:
        if self._disabled:
            return
        self._pressed = True
        self._redraw()

    def _release(self, _e) -> None:
        if self._disabled:
            return
        was_pressed = self._pressed
        self._pressed = False
        self._redraw()
        if was_pressed:
            self._on_click()

    def _redraw(self) -> None:
        w = int(self.winfo_width() or self._width or 1)
        h = int(self.winfo_height() or self._height or 1)
        self.delete("all")

        # shadow 4px
        so = self._shadow_offset
        dx = -1 if self._pressed else 0
        dy = -1 if self._pressed else 0
        shadow_pts = _rounded_rect_points(so + dx, so + dy, w + dx, h + dy, self._radius)
        self.create_polygon(shadow_pts, smooth=True, fill=self._shadow_color, outline="")

        fill = COLORS["panel"] if self._disabled else (self._hover_bg if getattr(self, "_hovering", False) else self._bg)
        fg = COLORS["muted"] if self._disabled else self._fg

        # main rounded rect
        main_pts = _rounded_rect_points(0 + dx, 0 + dy, w - so + dx, h - so + dy, self._radius)
        self.create_polygon(main_pts, smooth=True, fill=fill, outline="")

        # "increase" on press: slightly bigger text
        font = ("Segoe UI", 12, "bold") if self._pressed else self._font
        self.create_text((w - so) // 2 + dx, (h - so) // 2 + dy, text=self._text, fill=fg, font=font)


class CurrencyConverterApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Currency Converter")
        self.minsize(640, 420)
        self.geometry("720x480")
        self.configure(bg=COLORS["bg"])

        self._currencies: list[str] = []
        self._currency_set: set[str] = set()
        self._loading = False

        self._amount_var = tk.StringVar(value="")
        self._from_var = tk.StringVar(value="USD")
        self._to_var = tk.StringVar(value="EUR")
        self._result_var = tk.StringVar(value="")
        self._status_var = tk.StringVar(value="Loading currencies…")
        self._precision_var = tk.IntVar(value=2)
        self._currency_warning_var = tk.StringVar(value="")

        self._init_theme()
        self._build_ui()
        self._load_currencies_async()

    def _init_theme(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TFrame", background=COLORS["bg"])
        # Labels should blend with the main blue background (no dark boxes).
        style.configure("TLabel", background=COLORS["panel"], foreground=COLORS["text"])
        style.configure("Title.TLabel", background=COLORS["panel"], foreground=COLORS["text"])
        style.configure("Muted.TLabel", background=COLORS["panel"], foreground=COLORS["muted"])
        style.configure(
            "Neon.TCombobox",
            fieldbackground=COLORS["entry_bg"],
            background=COLORS["entry_bg"],
            foreground=COLORS["text"],
            arrowcolor=COLORS["text"],
            bordercolor=COLORS["entry_bg"],
            lightcolor=COLORS["entry_bg"],
            darkcolor=COLORS["entry_bg"],
        )
        style.map(
            "Neon.TCombobox",
            fieldbackground=[("readonly", COLORS["entry_bg"])],
            foreground=[("readonly", COLORS["text"])],
        )

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        root = tk.Frame(self, bg=COLORS["bg"])
        root.grid(row=0, column=0, sticky="nsew")
        root.columnconfigure(0, weight=1)

        panel = tk.Frame(root, bg=COLORS["panel"], bd=0, highlightthickness=0)
        panel.grid(row=0, column=0, sticky="nsew", padx=18, pady=18)
        panel.columnconfigure(0, weight=1)
        panel.columnconfigure(1, weight=1)
        for r in range(0, 9):
            panel.rowconfigure(r, weight=0)
        panel.rowconfigure(8, weight=1)

        title = ttk.Label(panel, text="Currency Converter", style="Title.TLabel", font=("Segoe UI", 18, "bold"))
        title.grid(row=0, column=0, columnspan=2, sticky="w", pady=(2, 14), padx=16)

        ttk.Label(panel, text="Amount").grid(row=1, column=0, columnspan=2, sticky="w", padx=16)
        amount_wrap = GlowWrap(panel, glow_color=COLORS["glow"], dim_color=COLORS["glow_dim"], pad=2)
        amount_wrap.grid(row=2, column=0, columnspan=2, sticky="ew", padx=16, pady=(6, 14))
        amount_entry = tk.Entry(
            amount_wrap,
            textvariable=self._amount_var,
            bg=COLORS["entry_bg"],
            fg=COLORS["text"],
            insertbackground=COLORS["text"],
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=("Segoe UI", 12),
        )
        amount_wrap.wrap(amount_entry)
        amount_entry.focus_set()

        ttk.Label(panel, text="From").grid(row=3, column=0, sticky="w", padx=16)
        ttk.Label(panel, text="To").grid(row=3, column=1, sticky="w", padx=16)

        from_wrap = GlowWrap(panel, glow_color=COLORS["glow"], dim_color=COLORS["glow_dim"], pad=2)
        to_wrap = GlowWrap(panel, glow_color=COLORS["glow"], dim_color=COLORS["glow_dim"], pad=2)
        from_wrap.grid(row=4, column=0, sticky="ew", padx=16, pady=(6, 12))
        to_wrap.grid(row=4, column=1, sticky="ew", padx=16, pady=(6, 12))

        # Editable comboboxes: user can type code, but still open dropdown list.
        self._from_box = ttk.Combobox(from_wrap, textvariable=self._from_var, state="normal", values=[], style="Neon.TCombobox")
        self._to_box = ttk.Combobox(to_wrap, textvariable=self._to_var, state="normal", values=[], style="Neon.TCombobox")
        from_wrap.wrap(self._from_box)
        to_wrap.wrap(self._to_box)

        opts = tk.Frame(panel, bg=COLORS["panel"])
        opts.grid(row=5, column=0, columnspan=2, sticky="ew", padx=16)
        # Swap left; precision controls right; spacer expands in the middle.
        opts.columnconfigure(1, weight=1)

        swap_btn = ShadowButton(
            opts,
            text="Swap",
            command=self._on_swap,
            bg=COLORS["button"],
            hover_bg=COLORS["button_hover"],
            fg=COLORS["button_text"],
            shadow_color=COLORS["shadow"],
            shadow_offset=4,
            height=48,
            width=120,  # >= 60px as requested
        )
        swap_btn.grid(row=0, column=0, sticky="w", pady=(0, 10))

        warn = ttk.Label(opts, textvariable=self._currency_warning_var, style="Muted.TLabel")
        warn.grid(row=0, column=1, sticky="w", padx=(12, 0), pady=(6, 0))

        ttk.Label(opts, text="Precision").grid(row=0, column=2, sticky="e", pady=(0, 10), padx=(0, 5))
        prec_wrap = GlowWrap(opts, glow_color=COLORS["glow"], dim_color=COLORS["glow_dim"], pad=2)
        prec_wrap.grid(row=0, column=3, sticky="e", pady=(0, 10))
        prec = tk.Spinbox(
            prec_wrap,
            from_=0,
            to=8,
            textvariable=self._precision_var,
            width=4,
            bg=COLORS["entry_bg"],
            fg=COLORS["text"],
            buttonbackground=COLORS["entry_bg"],
            insertbackground=COLORS["text"],
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=("Segoe UI", 11),
        )
        prec_wrap.wrap(prec)

        btns = tk.Frame(panel, bg=COLORS["panel"])
        btns.grid(row=6, column=0, columnspan=2, sticky="ew", padx=16, pady=(4, 6))
        btns.columnconfigure(0, weight=1)
        btns.columnconfigure(1, weight=1)

        self._convert_btn = ShadowButton(
            btns,
            text="Convert",
            command=self._on_convert,
            bg=COLORS["button"],
            hover_bg=COLORS["button_hover"],
            fg=COLORS["button_text"],
            shadow_color=COLORS["shadow"],
            shadow_offset=4,
            height=56,
        )
        self._reset_btn = ShadowButton(
            btns,
            text="New convert",
            command=self._on_reset,
            bg=COLORS["button"],
            hover_bg=COLORS["button_hover"],
            fg=COLORS["button_text"],
            shadow_color=COLORS["shadow"],
            shadow_offset=4,
            height=56,
        )
        self._convert_btn.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        self._reset_btn.grid(row=0, column=1, sticky="ew")

        result = ttk.Label(panel, textvariable=self._result_var, style="Title.TLabel", font=("Segoe UI", 13, "bold"))
        result.grid(row=7, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 0))

        status = ttk.Label(panel, textvariable=self._status_var, style="Muted.TLabel")
        status.grid(row=8, column=0, columnspan=2, sticky="w", padx=16, pady=(8, 16))

        self.bind("<Return>", lambda _e: self._on_convert())

        self._from_box.bind("<KeyRelease>", lambda _e: self._normalize_currency_input(self._from_var), add=True)
        self._to_box.bind("<KeyRelease>", lambda _e: self._normalize_currency_input(self._to_var), add=True)
        self._from_box.bind("<<ComboboxSelected>>", lambda _e: self._normalize_currency_input(self._from_var), add=True)
        self._to_box.bind("<<ComboboxSelected>>", lambda _e: self._normalize_currency_input(self._to_var), add=True)

    def _set_loading(self, value: bool, message: str | None = None) -> None:
        self._loading = value
        state = "disabled" if value else "normal"
        self._convert_btn.configure(state=state)
        self._reset_btn.configure(state=state)
        if message is not None:
            self._status_var.set(message)

    def _load_currencies_async(self) -> None:
        if self._loading:
            return

        def worker() -> None:
            try:
                rates = fetch_rates("USD", cache_ttl_seconds=DEFAULT_CACHE_TTL_SECONDS, force_refresh=False)
                currencies = sorted(set([rates.base_code] + list(rates.rates.keys())))
                self.after(0, lambda: self._on_currencies_loaded(currencies))
            except Exception as e:
                self.after(0, lambda: self._on_currencies_failed(e))

        self._set_loading(True, "Loading currencies…")
        threading.Thread(target=worker, daemon=True).start()

    def _on_currencies_loaded(self, currencies: list[str]) -> None:
        self._currencies = currencies
        self._currency_set = set(currencies)
        self._from_box.configure(values=currencies)
        self._to_box.configure(values=currencies)

        self._normalize_currency_input(self._from_var)
        self._normalize_currency_input(self._to_var)

        if self._from_var.get().upper() not in currencies:
            self._from_var.set("USD")
        if self._to_var.get().upper() not in currencies:
            self._to_var.set("EUR")

        self._set_loading(False, f"Loaded {len(currencies)} currencies.")
        self._currency_warning_var.set("")

    def _on_currencies_failed(self, e: Exception) -> None:
        self._set_loading(False, "Failed to load currencies.")
        messagebox.showerror("Error", f"Не удалось загрузить список валют.\n\n{e}")

    def _on_convert(self) -> None:
        if self._loading:
            return

        amount_text = self._amount_var.get().strip().replace(",", ".")
        if not amount_text:
            messagebox.showwarning("Input", "Введите сумму.")
            return

        try:
            amount = float(amount_text)
        except ValueError:
            messagebox.showwarning("Input", "Сумма должна быть числом.")
            return

        if amount < 0:
            messagebox.showwarning("Input", "Сумма должна быть неотрицательной.")
            return

        from_code = self._from_var.get().upper()
        to_code = self._to_var.get().upper()
        if not from_code or not to_code:
            messagebox.showwarning("Input", "Выберите валюты.")
            return

        if not self._validate_currency_pair(from_code, to_code, show_message=True):
            return

        def worker() -> None:
            try:
                # Fetch rates with base=from_code so conversion is stable and simple.
                rates = fetch_rates(from_code, cache_ttl_seconds=DEFAULT_CACHE_TTL_SECONDS, force_refresh=False)
                result = convert(amount, from_code, to_code, rates)
                self.after(0, lambda: self._show_result(amount, from_code, result, to_code))
            except RatesError as e:
                self.after(0, lambda: self._show_error(str(e)))
            except Exception as e:
                self.after(0, lambda: self._show_error(f"Unexpected error: {e}"))
            finally:
                self.after(0, lambda: self._set_loading(False, "Ready."))

        self._set_loading(True, "Converting…")
        threading.Thread(target=worker, daemon=True).start()

    def _show_result(self, amount: float, from_code: str, result: float, to_code: str) -> None:
        prec = int(self._precision_var.get())
        prec = 2 if prec < 0 else (8 if prec > 8 else prec)
        self._result_var.set(f"{amount:g} {from_code} = {result:.{prec}f} {to_code}")

    def _show_error(self, msg: str) -> None:
        messagebox.showerror("Error", msg)

    def _on_swap(self) -> None:
        a = self._from_var.get()
        b = self._to_var.get()
        self._from_var.set(b)
        self._to_var.set(a)
        self._normalize_currency_input(self._from_var)
        self._normalize_currency_input(self._to_var)
        self._validate_currency_pair(self._from_var.get().upper(), self._to_var.get().upper(), show_message=True)

    def _on_reset(self) -> None:
        self._amount_var.set("")
        self._from_var.set("USD")
        self._to_var.set("EUR")
        self._result_var.set("")
        self._precision_var.set(2)
        self._currency_warning_var.set("")
        if self._currencies:
            self._status_var.set("Ready.")
        else:
            self._status_var.set("Loading currencies…")

    def _normalize_currency_input(self, var: tk.StringVar) -> None:
        raw = var.get()
        if raw is None:
            return
        filtered = "".join(ch for ch in str(raw) if ch.isalpha())
        upper = filtered.upper()
        if upper != raw:
            var.set(upper)

        if self._currency_set and upper:
            self._validate_currency_pair(self._from_var.get().upper(), self._to_var.get().upper(), show_message=True)

    def _validate_currency_pair(self, from_code: str, to_code: str, *, show_message: bool) -> bool:
        if not self._currency_set:
            if show_message:
                self._currency_warning_var.set("")
            return True

        ok = (from_code in self._currency_set) and (to_code in self._currency_set)
        if ok:
            if show_message:
                self._currency_warning_var.set("")
            return True

        if show_message:
            self._currency_warning_var.set("Currency doesn't exist in the list")
        return False


def main() -> None:
    app = CurrencyConverterApp()
    app.mainloop()


if __name__ == "__main__":
    main()

