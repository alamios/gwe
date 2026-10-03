# SPDX-License-Identifier: GPL-3.0-or-later
"""Apply small, application-scoped GTK contrast fixes without selecting a theme."""


def prepare_windows(*windows):
    from gi.repository import Gtk
    provider = Gtk.CssProvider()
    provider.load_from_resource('/com/leinardi/gwe/ui/appearance.css')
    screens = set()
    for window in windows:
        window.get_style_context().add_class('gwe-window')
        screen = window.get_screen()
        if screen not in screens:
            # Desktop integration can load title-button rules at USER priority.
            # Override those only within the explicitly scoped GWE stylesheet.
            Gtk.StyleContext.add_provider_for_screen(screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
            screens.add(screen)
    return provider
