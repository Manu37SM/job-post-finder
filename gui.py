"""
Tkinter desktop GUI - mirrors mass-mailer's gui.py convention (Run tab,
Config tab, plus Review and Export tabs this project needs that mass-mailer
doesn't). This is a thin shell: every button callback calls straight into
GuiController (gui_controller.py), which holds all the actual logic and is
fully unit-tested on its own.

CANNOT BE VERIFIED IN THIS ENVIRONMENT - there is no display available
here (see README "Current limitations"). This file imports cleanly and its
widget-construction code follows standard Tkinter/ttk patterns, but has not
been visually run. If something looks wrong once you run it for real, the
fix belongs here, not in gui_controller.py - that module's own tests are
what to trust.

Run with: python gui.py
"""

import queue
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from gui_controller import GuiController

DEFAULT_CONFIG_PATH = "config.json"
DEFAULT_DB_PATH = "data/linkedin_recruiters.db"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("LinkedIn Recruiter Post Finder")
        self.geometry("900x600")

        self.controller = GuiController(config_path=DEFAULT_CONFIG_PATH, db_path=DEFAULT_DB_PATH)
        self._log_queue: queue.Queue[str] = queue.Queue()

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)

        self.run_tab = RunTab(notebook, self.controller, self._log_queue)
        self.review_tab = ReviewTab(notebook, self.controller)
        self.export_tab = ExportTab(notebook, self.controller)
        self.config_tab = ConfigTab(notebook, self.controller)

        notebook.add(self.run_tab, text="Run")
        notebook.add(self.review_tab, text="Review")
        notebook.add(self.export_tab, text="Export")
        notebook.add(self.config_tab, text="Config")

        # Switching to the Review tab should show whatever the latest run
        # produced, without the user needing a separate "Refresh" click.
        notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        self._notebook = notebook

        self._poll_log_queue()

    def _on_tab_changed(self, event):
        tab_text = self._notebook.tab(self._notebook.select(), "text")
        if tab_text == "Review":
            self.review_tab.refresh()
        elif tab_text == "Export":
            self.export_tab.refresh()

    def _poll_log_queue(self):
        try:
            while True:
                item = self._log_queue.get_nowait()
                # A ("__DONE__", None) sentinel means the background run
                # finished (success or error) - re-enable Start/Stop here,
                # on the main thread, rather than from the worker thread
                # that actually finished the run (Tkinter widgets can only
                # be touched from the main thread; this queue+poll pattern
                # is what makes that safe - see RunTab._on_done/_on_error).
                if isinstance(item, tuple) and item[0] == "__DONE__":
                    self.run_tab.finish_run_ui()
                else:
                    self.run_tab.append_log(item)
        except queue.Empty:
            pass
        self.after(200, self._poll_log_queue)


class RunTab(ttk.Frame):
    def __init__(self, parent, controller: GuiController, log_queue: "queue.Queue[str]"):
        super().__init__(parent)
        self.controller = controller
        self._log_queue = log_queue

        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=10)

        ttk.Label(top, text="Source:").grid(row=0, column=0, sticky="w")
        self.source_var = tk.StringVar(value="fixture")
        ttk.Radiobutton(top, text="Fixture (JSON)", variable=self.source_var, value="fixture").grid(
            row=0, column=1, sticky="w"
        )
        ttk.Radiobutton(top, text="Live LinkedIn", variable=self.source_var, value="live").grid(
            row=0, column=2, sticky="w"
        )

        ttk.Label(top, text="Path:").grid(row=1, column=0, sticky="w")
        self.path_var = tk.StringVar(value="data/sample_posts.json")
        ttk.Entry(top, textvariable=self.path_var, width=50).grid(row=1, column=1, columnspan=2, sticky="we")
        ttk.Button(top, text="Browse...", command=self._browse).grid(row=1, column=3)

        self.dry_run_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="Dry run", variable=self.dry_run_var).grid(row=2, column=0, sticky="w")

        button_row = ttk.Frame(self)
        button_row.pack(fill="x", padx=10)
        self.start_button = ttk.Button(button_row, text="Start", command=self._start)
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(button_row, text="Stop", command=self._stop, state="disabled")
        self.stop_button.pack(side="left", padx=5)

        self.log_text = tk.Text(self, height=25, state="disabled")
        self.log_text.pack(fill="both", expand=True, padx=10, pady=10)

    def _browse(self):
        path = filedialog.askopenfilename(title="Select fixture or session file")
        if path:
            self.path_var.set(path)

    def append_log(self, line: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _start(self):
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self._log_queue.put(f"Starting run (source={self.source_var.get()})...")

        if self.source_var.get() == "live":
            from linkedin.search import discover_posts as discover_fn
        else:
            from linkedin.fixture_source import discover_posts as discover_fn

        self.controller.start_run_async(
            discover_arg=self.path_var.get(),
            discover_fn=discover_fn,
            dry_run=self.dry_run_var.get(),
            on_done=self._on_done,
            on_error=self._on_error,
        )

    def _stop(self):
        self.controller.request_stop()
        self._log_queue.put("Stop requested - will finish the current post, then halt.")

    def finish_run_ui(self):
        """Called on the main thread only (via App._poll_log_queue's
        __DONE__ sentinel) - never call this directly from _on_done/_on_error,
        which run on the background worker thread and must never touch
        widgets themselves."""
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")

    def _on_done(self, summary):
        """Runs on the background worker thread (see GuiController.start_run_async)
        - must only enqueue data, never touch a widget directly."""
        lines = [
            f"Posts discovered:         {summary.posts_discovered}",
            f"Posts processed:          {summary.posts_processed}",
            f"Posts failed:             {summary.posts_failed}",
            f"Images found:             {summary.images_found}",
            f"Images processed:         {summary.images_processed}",
            f"OCR successes:            {summary.ocr_successes}",
            f"OCR failures:             {summary.ocr_failures}",
            f"Emails found:             {summary.emails_found}",
            f"Roles found:              {summary.roles_found}",
            f"Mumbai matches:           {summary.mumbai_matches}",
            f"Remote matches:           {summary.remote_matches}",
            f"Rejected locations:       {summary.rejected_locations}",
            f"Excluded (false positive): {summary.excluded}",
            f"Duplicates:               {summary.duplicates}",
            f"Records requiring review: {summary.records_requiring_review}",
            "Done. Switch to the Review tab to approve/reject/skip.",
        ]
        for line in lines:
            self._log_queue.put(line)
        self._log_queue.put(("__DONE__", None))

    def _on_error(self, exc):
        """Also runs on the background worker thread - see _on_done."""
        self._log_queue.put(f"ERROR: {exc}")
        self._log_queue.put(("__DONE__", None))


class ReviewTab(ttk.Frame):
    def __init__(self, parent, controller: GuiController):
        super().__init__(parent)
        self.controller = controller

        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=10, pady=10)

        columns = ("company", "job_role", "job_location", "work_mode", "email")
        self.tree = ttk.Treeview(paned, columns=columns, show="headings", selectmode="browse")
        for col in columns:
            self.tree.heading(col, text=col.replace("_", " ").title())
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        paned.add(self.tree, weight=3)

        right = ttk.Frame(paned)
        paned.add(right, weight=2)

        self.detail_text = tk.Text(right, height=20, state="disabled", wrap="word")
        self.detail_text.pack(fill="both", expand=True)

        button_row = ttk.Frame(right)
        button_row.pack(fill="x", pady=5)
        ttk.Button(button_row, text="Approve", command=lambda: self._decide("A")).pack(side="left")
        ttk.Button(button_row, text="Reject", command=lambda: self._decide("R")).pack(side="left", padx=5)
        ttk.Button(button_row, text="Skip", command=lambda: self._decide("S")).pack(side="left")
        ttk.Button(right, text="Refresh", command=self.refresh).pack(fill="x", pady=5)

        self._row_urls: dict[str, str] = {}  # tree item id -> post_url

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        self._row_urls.clear()
        for row in self.controller.get_review_rows():
            item_id = self.tree.insert(
                "", "end", values=(row.company, row.job_role, row.job_location, row.work_mode, row.email)
            )
            self._row_urls[item_id] = row.post_url

    def _on_select(self, event):
        selection = self.tree.selection()
        if not selection:
            return
        post_url = self._row_urls.get(selection[0])
        if not post_url:
            return
        detail = self.controller.get_review_detail(post_url) or "(no longer available)"
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("1.0", detail)
        self.detail_text.configure(state="disabled")

    def _decide(self, choice: str):
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("No selection", "Select a record first.")
            return
        post_url = self._row_urls.get(selection[0])
        if not post_url:
            return
        self.controller.decide(post_url, choice)
        self.refresh()


class ExportTab(ttk.Frame):
    def __init__(self, parent, controller: GuiController):
        super().__init__(parent)
        self.controller = controller

        self.status_label = ttk.Label(self, text="")
        self.status_label.pack(anchor="w", padx=10, pady=10)

        ttk.Button(self, text="Export approved -> data/approved_recruiters.xlsx", command=self._export).pack(
            padx=10, pady=5, anchor="w"
        )
        self.result_label = ttk.Label(self, text="")
        self.result_label.pack(anchor="w", padx=10, pady=10)

    def refresh(self):
        counts = self.controller.status_counts()
        text = ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())) or "(no records yet)"
        self.status_label.configure(text=f"Status counts - {text}")

    def _export(self):
        path, count = self.controller.export_for_mailer()
        self.result_label.configure(text=f"Wrote {count} approved record(s) to {path}")
        self.refresh()


class ConfigTab(ttk.Frame):
    """Edits the handful of config.json fields most worth changing from the
    GUI - mirrors mass-mailer's Config tab, which does the same for its own
    config.json rather than exposing every field."""

    FIELDS = [
        ("search_terms", "Search terms (comma-separated)"),
        ("target_roles", "Target roles (comma-separated)"),
        ("exclude_keywords", "Exclude keywords (comma-separated)"),
        ("max_posts", "Max posts"),
    ]

    def __init__(self, parent, controller: GuiController):
        super().__init__(parent)
        self.controller = controller
        self.vars: dict[str, tk.StringVar] = {}

        for i, (field_name, label) in enumerate(self.FIELDS):
            ttk.Label(self, text=label).grid(row=i, column=0, sticky="w", padx=10, pady=5)
            var = tk.StringVar()
            ttk.Entry(self, textvariable=var, width=60).grid(row=i, column=1, padx=10, pady=5)
            self.vars[field_name] = var

        ttk.Button(self, text="Load", command=self._load).grid(row=len(self.FIELDS), column=0, padx=10, pady=10)
        ttk.Button(self, text="Save", command=self._save).grid(row=len(self.FIELDS), column=1, padx=10, pady=10)

        self._load()

    def _load(self):
        try:
            config = self.controller.load_config()
        except FileNotFoundError:
            return
        self.vars["search_terms"].set(", ".join(config.search_terms))
        self.vars["target_roles"].set(", ".join(config.target_roles))
        self.vars["exclude_keywords"].set(", ".join(config.exclude_keywords))
        self.vars["max_posts"].set(str(config.max_posts))

    def _save(self):
        overrides = {
            "search_terms": [s.strip() for s in self.vars["search_terms"].get().split(",") if s.strip()],
            "target_roles": [s.strip() for s in self.vars["target_roles"].get().split(",") if s.strip()],
            "exclude_keywords": [
                s.strip() for s in self.vars["exclude_keywords"].get().split(",") if s.strip()
            ],
            "max_posts": int(self.vars["max_posts"].get() or 100),
        }
        self.controller.save_config(**overrides)
        messagebox.showinfo("Saved", f"Saved to {self.controller.config_path}")


def main():
    Path("data").mkdir(exist_ok=True)
    Path("logs").mkdir(exist_ok=True)
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
