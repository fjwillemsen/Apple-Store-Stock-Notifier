# macOS packaging support
from multiprocessing import freeze_support  # noqa

freeze_support()  # noqa

# # logging
# import sys
# sys.stdout = open("logs.txt", "w")

# UI
from nicegui import native, ui, run
from multiprocessing import Manager
from monitor import next_search_backoff


@ui.page("/")  # normal index page (e.g. the entry point of the app)
@ui.page(
    "/{_:path}"
)  # all other pages will be handled by the router but must be registered to also show the SPA index page
def main():
    # progressbar
    async def countdown_to_next_search():
        ui.notify("Searching...")
        # TODO do the actual search
        # await search_function()
        await run.cpu_bound(next_search_backoff, queue)
        await countdown_to_next_search()

    async def start_new_search(drawer):
        drawer.hide()
        progressbar.visible = True
        await countdown_to_next_search()

    # create a queue to communicate with the heavy computation process
    queue = Manager().Queue()
    # update the progress bar on the main process
    ui.timer(
        0.5,
        callback=lambda: progressbar.set_value(
            queue.get() if not queue.empty() else progressbar.value
        ),
    )
    # create the UI
    progressbar = ui.linear_progress(value=1, show_value=False).props(
        "instant-feedback"
    )
    progressbar.visible = False

    # menu and tabs
    with ui.header().classes(replace="row items-center") as header:
        ui.button(on_click=lambda: left_drawer.toggle(), icon="menu").props(
            "flat color=white"
        )
        with ui.tabs() as tabs:
            ui.tab("Results")
            ui.tab("Map")

    with ui.footer(value=False).classes("bg-red-100") as footer:
        ui.link(
            "Made in California by Floris-Jan Willemsen. Please donate: ❤️",
            "https://paypal.com",
            new_tab=True,
        )

    with ui.left_drawer(value=True, elevated=True).classes(
        "bg-blue-100"
    ) as left_drawer:
        ui.label("Side menu")
        ui.button(
            "Search", icon="search", on_click=lambda e: start_new_search(left_drawer)
        )

    with ui.page_sticky(position="bottom-right", x_offset=20, y_offset=20):
        ui.button(on_click=footer.toggle, icon="volunteer_activism").props("fab")

    with ui.tab_panels(tabs, value="Results").classes("w-full"):
        with ui.tab_panel("Results"):
            ui.label("↩ Open the search menu on the left to start searching 🔎")
            ui.label("Available locations:")
            with ui.list():
                ui.item("Location 1")
                ui.item("Location 2")
        with ui.tab_panel("Map"):
            ui.label("🛠️ Map functionality is coming soon! 🚧")
            # TODO https://nicegui.io/documentation/leaflet


ui.run(
    title="Apple Stock Notifier",
    reload=False,
    native=True,
    port=native.find_open_port(),
    dark=None,  # auto switch,
    favicon="assets/icon.jpg",
)
