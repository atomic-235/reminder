"""TUI Reminder Application using Textual."""

import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Static,
)
from textual.binding import Binding

from .env import get_last_error, get_telegram_credentials
from .logging import logger
from .parser import parse_meeting_time
from .telegram import TelegramBot


CONFIG_DIR = Path.home() / ".config" / "reminder"
CONFIG_FILE = CONFIG_DIR / "config.json"


@dataclass
class Settings:
    """Application settings that persist to disk."""

    theme: str = "textual-dark"

    @classmethod
    def load(cls) -> "Settings":
        """Load settings from config file, or return defaults."""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE) as f:
                    data = json.load(f)
                return cls(
                    **{k: v for k, v in data.items() if k in cls.__dataclass_fields__}
                )
            except (json.JSONDecodeError, TypeError):
                pass
        return cls()

    def save(self) -> None:
        """Save settings to config file."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(asdict(self), f, indent=2)

    def update(self, **kwargs: Any) -> None:
        """Update settings and save."""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.save()


class ReminderItem(ListItem):
    """A single reminder item in the list."""

    def __init__(
        self,
        reminder_id: str,
        reminder_time: datetime,
        message: str,
        *args: Any,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        self.reminder_id = reminder_id
        self.reminder_time = reminder_time
        self.message = message

    def compose(self) -> ComposeResult:
        time_str = self.reminder_time.strftime("%Y-%m-%d %H:%M")
        yield Static(f"[bold cyan]{time_str}[/] - {self.message}")


class ReminderApp(App[None]):
    """A TUI app for managing and sending Telegram reminders."""

    ENABLE_COMMAND_PALETTE = True

    CSS = """
    Screen {
        layout: grid;
        grid-size: 2;
        grid-columns: 1fr 2fr;
    }

    #sidebar {
        width: 100%;
        height: 100%;
        padding: 1;
    }

    #main {
        width: 100%;
        height: 100%;
        padding: 1 2;
    }

    #input-container {
        height: auto;
        margin-bottom: 1;
    }

    #meeting-input {
        margin-bottom: 1;
    }

    #message-input {
        margin-bottom: 1;
    }

    #button-container {
        height: auto;
        margin-bottom: 1;
    }

    #button-container Button {
        margin-right: 1;
    }

    #status {
        height: auto;
        padding: 1;
        margin-top: 1;
        background: $surface;
        border: solid $primary;
        color: $text;
    }

    #reminder-list {
        height: 100%;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("n", "focus_meeting", "New Meeting"),
        Binding("m", "focus_message", "Custom Message"),
        Binding("d", "delete_reminder", "Delete"),
        Binding("t", "send_test", "Send Test"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.settings = Settings.load()
        self.theme = self.settings.theme
        self.reminders: dict[str, tuple[datetime, str, asyncio.Task[None]]] = {}
        self.reminder_counter = 0
        self.bot: TelegramBot | None = None

    def watch_theme(self, theme: str) -> None:
        """Save theme when it changes."""
        if hasattr(self, "settings"):
            self.settings.update(theme=theme)

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="sidebar"):
            yield Label("[bold]Scheduled Reminders[/]")
            yield ListView(id="reminder-list")
        with Vertical(id="main"):
            yield Label("[bold]Paste Meeting Time[/]")
            yield Label("[dim]Formats: 11:30 or Thu 29/01/2026 10:00 - 11:00[/]")
            with Container(id="input-container"):
                yield Input(
                    placeholder="Meeting time (e.g., 11:30 or Thu 29/01/2026 10:00 - 11:00)",
                    id="meeting-input",
                )
                yield Input(
                    placeholder="Meeting description (optional)",
                    id="message-input",
                )
            with Horizontal(id="button-container"):
                yield Button("Schedule Meeting", id="btn-meeting", variant="primary")
                yield Button("Send Test", id="btn-test", variant="default")
            yield Static("Ready", id="status")
        yield Footer()

    async def on_mount(self) -> None:
        """Initialize the app and load Telegram credentials."""
        logger.info("App mounted, loading credentials")
        self.update_status("Loading Telegram credentials...")
        token, chat_id = get_telegram_credentials()

        if not token or not chat_id:
            error = get_last_error() or "Unknown error"
            logger.error(f"Credentials missing: {error}")
            self.update_status(
                f"[red]Error: {error}. Token: {bool(token)}, ChatID: {bool(chat_id)}[/]"
            )
            return

        self.bot = TelegramBot(token, chat_id)

        # Test connection
        logger.info("Testing Telegram connection")
        if await self.bot.test_connection():
            logger.info("Connection successful")
            self.update_status("[green]Connected to Telegram bot[/]")
        else:
            logger.error("Connection failed")
            self.update_status("[red]Failed to connect to Telegram bot[/]")

    def update_status(self, message: str) -> None:
        """Update the status display."""
        status = self.query_one("#status", Static)
        status.update(message)

    def action_focus_meeting(self) -> None:
        """Focus the meeting input."""
        self.query_one("#meeting-input", Input).focus()

    def action_focus_message(self) -> None:
        """Focus the message input."""
        self.query_one("#message-input", Input).focus()

    async def action_test_connection(self) -> None:
        """Test the Telegram bot connection."""
        if not self.bot:
            self.update_status("[red]Bot not initialized![/]")
            return

        self.update_status("Testing connection...")
        if await self.bot.test_connection():
            self.update_status("[green]Connection successful![/]")
        else:
            self.update_status("[red]Connection failed![/]")

    def action_delete_reminder(self) -> None:
        """Delete the selected reminder."""
        list_view = self.query_one("#reminder-list", ListView)
        if list_view.highlighted_child is not None:
            item = list_view.highlighted_child
            if isinstance(item, ReminderItem) and item.reminder_id in self.reminders:
                _, _, task = self.reminders.pop(item.reminder_id)
                task.cancel()
                item.remove()
                self.update_status("[yellow]Reminder deleted[/]")

    def _generate_reminder_id(self) -> str:
        """Generate a unique reminder ID."""
        self.reminder_counter += 1
        return f"reminder_{self.reminder_counter}"

    def _schedule_reminder(self, reminder_time: datetime, message: str) -> str | None:
        """Schedule a single reminder. Returns reminder ID or None if time is in past."""
        now = datetime.now()
        if reminder_time <= now:
            return None

        delay_seconds = (reminder_time - now).total_seconds()
        reminder_id = self._generate_reminder_id()
        task = asyncio.create_task(
            self._send_delayed_reminder(reminder_id, message, delay_seconds)
        )
        self.reminders[reminder_id] = (reminder_time, message, task)

        # Add to list view
        list_view = self.query_one("#reminder-list", ListView)
        list_view.append(ReminderItem(reminder_id, reminder_time, message))

        return reminder_id

    @on(Button.Pressed, "#btn-meeting")
    def schedule_meeting_reminders(self) -> None:
        """Schedule reminders for a meeting (5 min before and at start)."""
        meeting_str = self.query_one("#meeting-input", Input).value.strip()
        description = self.query_one("#message-input", Input).value.strip()

        if not meeting_str:
            self.update_status("[red]Please paste a meeting time![/]")
            return

        meeting = parse_meeting_time(meeting_str)
        if not meeting:
            self.update_status(
                "[red]Invalid format! Use: 11:30 or Thu 29/01/2026 10:00 - 11:00[/]"
            )
            return

        now = datetime.now()
        scheduled_count = 0
        meeting_label = description or f"Meeting {meeting.start.strftime('%H:%M')}"

        # Schedule 5 minutes before
        five_min_before = meeting.start - timedelta(minutes=5)
        if five_min_before > now:
            msg = f"5 min warning: {meeting_label} starts at {meeting.start.strftime('%H:%M')}"
            if self._schedule_reminder(five_min_before, msg):
                scheduled_count += 1

        # Schedule at meeting start
        if meeting.start > now:
            msg = f"Starting NOW: {meeting_label}"
            if self._schedule_reminder(meeting.start, msg):
                scheduled_count += 1

        if scheduled_count > 0:
            self.update_status(
                f"[green]Scheduled {scheduled_count} reminder(s) for {meeting_label}[/]"
            )
            # Clear inputs
            self.query_one("#meeting-input", Input).value = ""
            self.query_one("#message-input", Input).value = ""
        else:
            self.update_status("[yellow]Meeting time is in the past![/]")

    @on(Button.Pressed, "#btn-test")
    async def send_test_message(self) -> None:
        """Send a test message immediately."""
        await self.action_send_test()

    async def action_send_test(self) -> None:
        """Send a test message (action for keybinding)."""
        logger.info("Send test triggered")
        self.update_status("Sending test message...")
        await self._send_telegram_message("Test reminder from TUI app")

    async def _send_delayed_reminder(
        self, reminder_id: str, message: str, delay_seconds: float
    ) -> None:
        """Wait and then send the reminder."""
        try:
            await asyncio.sleep(delay_seconds)
            await self._send_telegram_message(message)
        finally:
            # Remove from reminders dict and list view
            if reminder_id in self.reminders:
                del self.reminders[reminder_id]
                # Find and remove from list view
                list_view = self.query_one("#reminder-list", ListView)
                for child in list_view.children:
                    if (
                        isinstance(child, ReminderItem)
                        and child.reminder_id == reminder_id
                    ):
                        child.remove()
                        break

    async def _send_telegram_message(self, message: str) -> None:
        """Send a message via Telegram."""
        logger.info(f"Sending message: {message[:50]}")
        if not self.bot:
            logger.error("Bot not initialized")
            self.update_status("[red]Bot not initialized![/]")
            return

        try:
            await self.bot.send_message(f"🔔 {message}")
            logger.info("Message sent successfully")
            self.update_status(f"[green]Sent: {message[:40]}[/]")
        except Exception as e:
            logger.error(f"Failed to send: {e}")
            self.update_status(f"[red]Failed to send: {e}[/]")


def main() -> None:
    """Entry point for the reminder app."""
    app = ReminderApp()
    app.run()


if __name__ == "__main__":
    main()
