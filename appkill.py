#!/usr/bin/env python3
"""AppKill - macOS Application Manager with Textual UI."""

import signal
from dataclasses import dataclass
from typing import ClassVar

import psutil
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Static


# =============================================================================
# Section 1: Process Detection
# =============================================================================


def get_running_apps() -> list[dict]:
    """Get all running applications using psutil with macOS-specific filtering."""
    apps = []

    # First call to initialize CPU percent (psutil quirk)
    for proc in psutil.process_iter(['pid']):
        try:
            proc.cpu_percent()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info', 'status']):
        try:
            info = proc.info
            name = info.get('name', '')

            # Filter out system processes and daemons
            if not name:
                continue
            if name.startswith('_'):
                continue
            if name.startswith('.'):
                continue
            if name in ('kernel_task', 'launchd', 'syslogd', 'configd'):
                continue

            # Check if this is a GUI app (has .app bundle)
            is_gui_app = False
            try:
                exe_path = proc.exe()
                if '.app/' in exe_path or '/Applications/' in exe_path:
                    is_gui_app = True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

            # Get memory info
            mem_info = info.get('memory_info')
            memory = mem_info.rss if mem_info else 0

            # Get CPU percent
            cpu = info.get('cpu_percent', 0.0) or 0.0

            apps.append({
                'pid': info['pid'],
                'name': name,
                'cpu': cpu,
                'memory': memory,
                'status': info.get('status', 'unknown'),
                'is_gui_app': is_gui_app,
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    return apps


def get_status_indicator(app: dict) -> tuple[str, str]:
    """Get visual status indicator and style for an app."""
    cpu = app.get('cpu', 0)
    memory = app.get('memory', 0)

    # High CPU (>50%)
    if cpu > 50:
        return '●', 'yellow'
    # High memory (>1GB)
    if memory > 1_000_000_000:
        return '●', 'red'
    # Normal
    return '●', 'green'


# =============================================================================
# Section 2: Process Actions
# =============================================================================


def kill_app(pid: int, force: bool = False) -> tuple[bool, str]:
    """Kill an application by PID.

    Args:
        pid: Process ID to kill
        force: If True, use SIGKILL; otherwise use SIGTERM

    Returns:
        Tuple of (success, message)
    """
    try:
        proc = psutil.Process(pid)
        proc_name = proc.name()

        if force:
            proc.kill()  # SIGKILL
            return True, f"Force killed {proc_name} (PID: {pid})"
        else:
            proc.terminate()  # SIGTERM
            return True, f"Terminated {proc_name} (PID: {pid})"
    except psutil.NoSuchProcess:
        return False, f"Process {pid} no longer exists"
    except psutil.AccessDenied:
        return False, f"Access denied - try running with sudo"
    except Exception as e:
        return False, f"Error killing process: {e}"


def get_process_details(pid: int) -> dict | None:
    """Get detailed information about a process."""
    try:
        proc = psutil.Process(pid)
        return {
            'pid': pid,
            'name': proc.name(),
            'status': proc.status(),
            'cpu_percent': proc.cpu_percent(),
            'memory_info': proc.memory_info(),
            'create_time': proc.create_time(),
            'cmdline': proc.cmdline(),
        }
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None


# =============================================================================
# Section 3: Data Processing
# =============================================================================


def parse_apps(apps: list[dict]) -> list[dict]:
    """Normalize and sort app data: GUI apps first, then by memory usage (descending)."""
    # Sort by: 1) GUI apps first, 2) memory usage highest first
    return sorted(apps, key=lambda x: (not x.get('is_gui_app', False), -x.get('memory', 0)))


def format_memory(bytes_val: int) -> str:
    """Format bytes as human-readable memory string."""
    if bytes_val < 1024:
        return f"{bytes_val} B"
    elif bytes_val < 1024 * 1024:
        return f"{bytes_val / 1024:.1f} KB"
    elif bytes_val < 1024 * 1024 * 1024:
        return f"{bytes_val / (1024 * 1024):.1f} MB"
    else:
        return f"{bytes_val / (1024 * 1024 * 1024):.2f} GB"


def format_cpu(percent: float) -> str:
    """Format CPU percentage."""
    return f"{percent:.1f}%"


def calculate_totals(apps: list[dict]) -> dict:
    """Calculate total stats from app list."""
    total_cpu = sum(app.get('cpu', 0) for app in apps)
    total_memory = sum(app.get('memory', 0) for app in apps)

    # Get system memory info
    vm = psutil.virtual_memory()

    return {
        'count': len(apps),
        'cpu': total_cpu,
        'memory_used': vm.used,
        'memory_total': vm.total,
    }


# =============================================================================
# Section 4: Custom Widgets
# =============================================================================


class StatsBar(Static):
    """Shows total apps, total memory, total CPU."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.stats = {'count': 0, 'cpu': 0.0, 'memory_used': 0, 'memory_total': 0}

    def update_stats(self, stats: dict) -> None:
        """Update the displayed statistics."""
        self.stats = stats
        self.refresh_display()

    def refresh_display(self) -> None:
        """Refresh the stats display."""
        count = self.stats.get('count', 0)
        cpu = self.stats.get('cpu', 0)
        memory_used = self.stats.get('memory_used', 0)
        memory_total = self.stats.get('memory_total', 0)

        self.update(
            f" Apps: [bold]{count}[/bold] │ "
            f"CPU: [bold]{format_cpu(cpu)}[/bold] │ "
            f"Memory: [bold]{format_memory(memory_used)}[/bold] / {format_memory(memory_total)}"
        )


class SearchInput(Input):
    """Custom search input widget."""

    def __init__(self, **kwargs):
        super().__init__(placeholder="Search apps...", **kwargs)


@dataclass
class AppInfo:
    """Information about an app to kill."""
    pid: int
    name: str


class ConfirmDialog(ModalScreen[bool]):
    """Modal dialog for kill confirmation."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "confirm", "Confirm"),
    ]

    def __init__(self, app_info: AppInfo, force: bool = False):
        super().__init__()
        self.app_info = app_info
        self.force = force

    def compose(self) -> ComposeResult:
        action = "Force kill" if self.force else "Kill"
        yield Grid(
            Label(f"{action} [bold]{self.app_info.name}[/bold]?", id="dialog-title"),
            Label(f"PID: {self.app_info.pid}", id="dialog-pid"),
            Horizontal(
                Button("Cancel", id="cancel", variant="default"),
                Button(action, id="confirm", variant="error"),
                id="dialog-buttons",
            ),
            id="confirm-dialog",
        )

    def action_cancel(self) -> None:
        """Cancel the dialog."""
        self.dismiss(False)

    def action_confirm(self) -> None:
        """Confirm the action."""
        self.dismiss(True)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "cancel":
            self.dismiss(False)
        elif event.button.id == "confirm":
            self.dismiss(True)


# =============================================================================
# Section 5: TCSS Styling
# =============================================================================


CSS = """
Screen {
    background: $surface;
}

Header {
    dock: top;
    background: $primary;
}

Footer {
    dock: bottom;
}

#stats-bar {
    dock: top;
    height: 1;
    background: $surface-darken-1;
    padding: 0 1;
}

#search-container {
    dock: top;
    height: auto;
    padding: 0 1;
    display: none;
}

#search-container.visible {
    display: block;
}

#search-input {
    width: 100%;
    margin: 0;
}

#app-table {
    height: 1fr;
}

DataTable {
    height: 100%;
}

DataTable > .datatable--cursor {
    background: $accent;
}

#message-bar {
    dock: bottom;
    height: 1;
    background: $surface-darken-1;
    padding: 0 1;
    display: none;
}

#message-bar.visible {
    display: block;
}

#message-bar.success {
    background: $success;
    color: $text;
}

#message-bar.error {
    background: $error;
    color: $text;
}

/* Confirm Dialog Styling */
ConfirmDialog {
    align: center middle;
}

#confirm-dialog {
    width: 50;
    height: auto;
    padding: 1 2;
    background: $surface;
    border: thick $primary;
    grid-size: 1;
    grid-rows: auto auto auto;
}

#dialog-title {
    text-align: center;
    width: 100%;
    margin-bottom: 1;
}

#dialog-pid {
    text-align: center;
    width: 100%;
    color: $text-muted;
    margin-bottom: 1;
}

#dialog-buttons {
    width: 100%;
    height: auto;
    align: center middle;
}

#dialog-buttons Button {
    margin: 0 1;
}

/* Status colors */
.status-green {
    color: $success;
}

.status-yellow {
    color: $warning;
}

.status-red {
    color: $error;
}
"""


# =============================================================================
# Section 6: Main Application
# =============================================================================


class AppKillApp(App):
    """Main Textual application for killing macOS apps."""

    TITLE = "Pandora"
    SUB_TITLE = "Open the box"
    CSS = CSS

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("q", "quit", "Quit"),
        Binding("k", "kill_app", "Kill"),
        Binding("K", "force_kill_app", "Force Kill"),
        Binding("r", "refresh", "Refresh"),
        Binding("/", "search", "Search"),
        Binding("escape", "clear_search", "Clear", show=False),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("up", "cursor_up", "Up", show=False),
    ]

    def __init__(self):
        super().__init__()
        self.apps: list[dict] = []
        self.filtered_apps: list[dict] = []
        self.search_visible = False
        self.pending_kill: AppInfo | None = None
        self.pending_force: bool = False

    def compose(self) -> ComposeResult:
        """Compose the application layout."""
        yield Header()
        yield StatsBar(id="stats-bar")
        yield Vertical(
            SearchInput(id="search-input"),
            id="search-container",
        )
        yield DataTable(id="app-table")
        yield Static("", id="message-bar")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the application on mount."""
        table = self.query_one("#app-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True

        # Add columns
        table.add_column("", key="status", width=3)
        table.add_column("Name", key="name", width=30)
        table.add_column("PID", key="pid", width=10)
        table.add_column("CPU%", key="cpu", width=10)
        table.add_column("Memory", key="memory", width=12)
        table.add_column("Status", key="proc_status", width=12)

        # Load apps
        self.load_apps()

    @work(exclusive=True, thread=True)
    def load_apps(self) -> None:
        """Load apps in background thread."""
        apps = get_running_apps()
        self.call_from_thread(self.update_app_list, apps)

    def update_app_list(self, apps: list[dict]) -> None:
        """Update the app list in the UI."""
        self.apps = parse_apps(apps)
        self.apply_filter()

    def apply_filter(self) -> None:
        """Apply current search filter to apps."""
        search_input = self.query_one("#search-input", SearchInput)
        search_term = search_input.value.lower().strip()

        if search_term:
            self.filtered_apps = [
                app for app in self.apps
                if search_term in app['name'].lower()
            ]
        else:
            self.filtered_apps = self.apps.copy()

        self.refresh_table()
        self.refresh_stats()

    def refresh_table(self) -> None:
        """Refresh the data table with current filtered apps."""
        table = self.query_one("#app-table", DataTable)
        table.clear()

        for app in self.filtered_apps:
            indicator, color = get_status_indicator(app)
            styled_indicator = f"[{color}]{indicator}[/{color}]"

            table.add_row(
                styled_indicator,
                app['name'],
                str(app['pid']),
                format_cpu(app['cpu']),
                format_memory(app['memory']),
                app['status'],
                key=str(app['pid']),
            )

    def refresh_stats(self) -> None:
        """Refresh the stats bar."""
        stats_bar = self.query_one("#stats-bar", StatsBar)
        stats = calculate_totals(self.filtered_apps)
        stats_bar.update_stats(stats)

    def show_message(self, message: str, is_error: bool = False) -> None:
        """Show a message in the message bar."""
        message_bar = self.query_one("#message-bar", Static)
        message_bar.update(f" {message}")
        message_bar.remove_class("success", "error")
        message_bar.add_class("visible")
        message_bar.add_class("error" if is_error else "success")

        # Auto-hide after 3 seconds
        self.set_timer(3.0, self.hide_message)

    def hide_message(self) -> None:
        """Hide the message bar."""
        message_bar = self.query_one("#message-bar", Static)
        message_bar.remove_class("visible")

    def get_selected_app(self) -> dict | None:
        """Get the currently selected app."""
        table = self.query_one("#app-table", DataTable)
        if table.row_count == 0:
            return None

        try:
            row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
            pid = int(row_key.value)
            for app in self.filtered_apps:
                if app['pid'] == pid:
                    return app
        except Exception:
            pass

        return None

    def action_quit(self) -> None:
        """Quit the application."""
        self.exit()

    def action_refresh(self) -> None:
        """Refresh the app list."""
        self.show_message("Refreshing...")
        self.load_apps()

    def action_search(self) -> None:
        """Show/focus the search input."""
        container = self.query_one("#search-container")
        search_input = self.query_one("#search-input", SearchInput)

        container.add_class("visible")
        self.search_visible = True
        search_input.focus()

    def action_clear_search(self) -> None:
        """Clear search and hide search input."""
        container = self.query_one("#search-container")
        search_input = self.query_one("#search-input", SearchInput)

        if self.search_visible:
            search_input.value = ""
            container.remove_class("visible")
            self.search_visible = False
            self.apply_filter()

            # Focus back on table
            table = self.query_one("#app-table", DataTable)
            table.focus()

    def action_cursor_down(self) -> None:
        """Move cursor down in the table."""
        table = self.query_one("#app-table", DataTable)
        table.action_cursor_down()

    def action_cursor_up(self) -> None:
        """Move cursor up in the table."""
        table = self.query_one("#app-table", DataTable)
        table.action_cursor_up()

    def action_kill_app(self) -> None:
        """Kill the selected app (graceful SIGTERM)."""
        app = self.get_selected_app()
        if app:
            self.pending_kill = AppInfo(pid=app['pid'], name=app['name'])
            self.pending_force = False
            self.push_screen(
                ConfirmDialog(self.pending_kill, force=False),
                self.on_confirm_dialog_dismiss,
            )

    def action_force_kill_app(self) -> None:
        """Force kill the selected app (SIGKILL)."""
        app = self.get_selected_app()
        if app:
            self.pending_kill = AppInfo(pid=app['pid'], name=app['name'])
            self.pending_force = True
            self.push_screen(
                ConfirmDialog(self.pending_kill, force=True),
                self.on_confirm_dialog_dismiss,
            )

    def on_confirm_dialog_dismiss(self, confirmed: bool) -> None:
        """Handle confirm dialog dismissal."""
        if confirmed and self.pending_kill:
            self.do_kill_app(self.pending_kill.pid, self.pending_force)
        self.pending_kill = None
        self.pending_force = False

    @work(thread=True)
    def do_kill_app(self, pid: int, force: bool) -> None:
        """Kill app in background thread."""
        success, message = kill_app(pid, force)
        self.call_from_thread(self.on_kill_complete, success, message)

    def on_kill_complete(self, success: bool, message: str) -> None:
        """Handle kill completion."""
        self.show_message(message, is_error=not success)
        if success:
            # Refresh the list after a short delay
            self.set_timer(0.5, self.load_apps)

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes."""
        if event.input.id == "search-input":
            self.apply_filter()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle search input submission."""
        if event.input.id == "search-input":
            # Focus back on table
            table = self.query_one("#app-table", DataTable)
            table.focus()


def main():
    """Entry point for the application."""
    app = AppKillApp()
    app.run()


if __name__ == "__main__":
    main()
