import client.api as api
from client import display as d
from client.donation import run_donation


_IN_PROGRESS = {"available", "claimed"}
_HISTORY = {"completed", "missed"}


def _task_summary(task: dict) -> str:
    time_range = d.fmt_time_range(task.get("start_time"), task.get("end_time"))
    addr = d.fmt_address(task.get("address", {}))
    status_badge = f"[{task['status'].upper()}]" if task["status"] in _HISTORY else ""
    line = f"{task['donor_name']:<28}  {time_range}  {status_badge}"
    return f"{line}\n     {d.fmt_date(task['date'])} · {addr}"


def run_my_tasks(session: dict):
    view = "in_progress"

    while True:
        d.header(f"REPLATE — My Tasks ({'In Progress' if view == 'in_progress' else 'History'})")
        d.blank()

        try:
            all_tasks = api.get("/api/my_tasks", token=session["token"])
        except api.ApiError as e:
            d.error(str(e))
            return

        tasks = (
            [t for t in all_tasks if t["status"] in _IN_PROGRESS]
            if view == "in_progress"
            else [t for t in all_tasks if t["status"] in _HISTORY]
        )
        tasks.sort(key=lambda t: t.get("date", ""))

        if not tasks:
            d.info("No tasks here yet.")
        else:
            for i, task in enumerate(tasks, 1):
                print(f"  {i:>2}. {_task_summary(task)}")
                d.blank()

        d.divider()
        toggle_label = "Switch to History" if view == "in_progress" else "Switch to In Progress"
        options = [toggle_label]
        if tasks and view == "in_progress":
            options.append("Log a completion / miss")
        choice = d.menu(options, back_label="Main menu")

        if choice == "b":
            return
        elif choice == "1":
            view = "history" if view == "in_progress" else "in_progress"
        elif choice == "2" and tasks and view == "in_progress":
            labels = [task["donor_name"] for task in tasks]
            idx = d.choose("Select a task", labels)
            if idx is not None:
                run_donation(tasks[idx], session)
        else:
            d.error("Invalid choice.")
