from gi.repository import Gtk, GLib, Gio, Gdk, Pango
from threading import Timer

from .threads import StdInReader
from .console import Console, ConsoleError, Rules, FreeForAll, Beacons
from .sql import sql_create, sql_open, SQLError
from . import rest


class UserDialog(Gtk.Dialog):
    def __init__(self, parent, title, generate):
        Gtk.Dialog.__init__(self, title, parent, Gtk.DialogFlags.MODAL)
        button = self.add_button('Fermer', 0)
        button.set_image(Gtk.Image(icon_name='window-close'))
        button.set_always_show_image(True)

        self._generate = generate
        self.get_content_area().add(self._do_generate())

        self.show_all()

    def _do_generate(self):
        return self._generate()


class WaitDialog(UserDialog):
    def __init__(self, parent, main_text, secondary_text):
        self._main = main_text
        self._secondary = secondary_text
        super().__init__(parent, 'Oups', None)
        
    def _do_generate(self):
        hbox = Gtk.HBox()
        vbox = Gtk.VBox(spacing=1)
        vbox.set_margin_top(10)
        vbox.set_margin_bottom(10)
        vbox.set_margin_right(10)
        vbox.set_margin_left(10)
        label = Gtk.Label()
        label.set_markup('<b><big>{}</big></b>'.format(self._main))
        vbox.pack_start(label, True, True, 0)
        label = Gtk.Label(label=self._secondary)
        label.set_line_wrap(True)
        vbox.pack_start(label, False, False, 0)
        image = Gtk.Image(icon_name='dialog-error',
                          icon_size=Gtk.IconSize.DIALOG)
        hbox.pack_start(image, False, False, 0)
        hbox.pack_start(vbox, False, False, 0)
        return hbox


class DroneRacer(Gtk.Application):
    def __init__(self, fancy=False):
        Gtk.Application.__init__(self)
        self.set_application_id('org.race.drone')
        self.set_flags(0)
        self.fancy = fancy
        self.connect('startup', self.on_startup)
        self.connect('activate', self.on_activate)
        self.connect('shutdown', self.on_shutdown)

    def on_startup(self, app):
        self.window = DroneRacerWindow(app, self.fancy)
        app.add_window(self.window)
        builder = Gtk.Builder.new_from_file('resources/ui/menubar.ui')
        builder.connect_signals(app)
        app.set_app_menu(builder.get_object('appmenu'))
        app.set_menubar(builder.get_object('menubar'))

        self._connect_action('win_new_dialog', self.window.new_database)
        self._connect_action('win_open_dialog', self.window.open_database)
        self._connect_action('win_close', self.window.close_database)
        self._connect_action('quit', lambda a,u: self.quit())

        self._connect_action('win_register_dialog',
                self.show_dialog, 'registration_dialog')
        self._connect_action(
                'dialog_categories',
                self.create_dialog,
                'Gestion de la catégorie d’un drone',
                self.window.create_manage_categories)
        self._connect_action('win_game_dialog',
                self.show_dialog, 'game_dialog')
        self._connect_action('rest', self.manage_rest_server)

    def on_activate(self, app):
        self.window.show_all()

    def on_shutdown(self, app):
        self.window.shutdown()

    def _connect_action(self, name, callback, *extra_args):
        action = Gio.SimpleAction.new(name, None)
        action.connect('activate', callback, *extra_args)
        self.add_action(action)

    def show_dialog(self, action, u_data, attr_name):
        if self.window.beacon_names is None:
            dialog = WaitDialog(self.window,
                    'Aucune base de donnée connectée',
                    'Ouvrez ou créez une base de donnée '
                    'avant d’utiliser cette action.')
            dialog.run()
            dialog.destroy()
        else:
            dialog = getattr(self.window, attr_name)
            dialog.show_all()
            dialog.run()
            dialog.hide()

    def create_dialog(self, action, u_data, title, generate_content):
        if self.window.beacon_names is None:
            dialog = WaitDialog(self.window,
                    'Aucune base de donnée connectée',
                    'Ouvrez ou créez une base de donnée '
                    'avant d’utiliser cette action.')
        else:
            dialog = UserDialog(self.window, title, generate_content)
        dialog.run()
        dialog.destroy()

    def manage_rest_server(self, action, user_data):
        dialog = Gtk.Dialog('REST server', self.window, Gtk.DialogFlags.MODAL)
        dialog.set_border_width(5)
        button = dialog.add_button('Annuler', Gtk.ResponseType.CANCEL)
        button.set_image(Gtk.Image(icon_name='window-close'))
        button.set_always_show_image(True)
        button = dialog.add_button('Enregistrer', Gtk.ResponseType.OK)
        button.set_image(Gtk.Image(icon_name='document-save'))
        button.set_always_show_image(True)
        box = Gtk.VBox()
        box.set_margin_bottom(10)
        dialog.get_content_area().add(box)
        box.pack_start(Gtk.Label('Adresse web de l’API REST'), True, True, 1)
        entry = Gtk.Entry()
        entry.set_text(rest._REST_ADDR)
        box.pack_start(entry, False, False, 1)
        dialog.show_all()
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            rest._REST_ADDR = entry.get_text()
        dialog.destroy()

    def manage_categories(self, action, user_data):
        if self.window.beacon_names is None:
            dialog = WaitDialog(self.window,
                    'Aucune base de donnée connectée',
                    'Ouvrez ou créez une base de donnée '
                    'avant d’utiliser cette action.')
        else:
            dialog = Gtk.Dialog(
                    'Gestion des catégories de drones',
                    self.window, Gtk.DialogFlags.MODAL)
            #dialog.get_content_area().add(self.window.create_categories())
            dialog.get_content_area().add(Gtk.Label('hello'))
            button = self.add_button('Fermer', 0)
            button.set_image(Gtk.Image(icon_name='window-close'))
            button.set_always_show_image(True)
            dialog.show_all()
        dialog.run()
        dialog.destroy()

        
class DroneRacerWindow(Gtk.ApplicationWindow):
    def __init__(self, application, fancy=False):
        # Attributs hors Gtk
        self.console = Console(self.get_time, self.update_race)
        self.reader_thread = StdInReader(self.console)
        self.reader_thread.start()
        self.db = None
        self.beacon_names = None

        # Paramètres de base
        Gtk.ApplicationWindow.__init__(self,
                title='Drone Racer', application=application)
        self.set_border_width(0)
        self.set_default_size(900, 400)
        self.override_background_color(Gtk.StateFlags.NORMAL,
                Gdk.RGBA(1, 1, 1, 1))
        #self.maximize()

        if fancy:
            header = Gtk.HeaderBar(title='Drone Racer')
            header.set_subtitle('Bienvenue')
            header.props.show_close_button = True
            header.set_border_width(0)
            self.set_titlebar(header)
            self.set_custom_title = header.set_subtitle
        else:
            self.set_custom_title =\
                    lambda text: self.set_title(text + ' | Drone Racer')

        # Éléments partagés entre différentes fonctions
        self.event_dropdown = Gtk.ComboBoxText.new_with_entry()
        self.event_dropdown.connect('changed', self._on_event_selected)
        self.event_entry = Gtk.Entry()
        self.driver_dropdown = Gtk.ComboBoxText.new_with_entry()
        self.driver_dropdown.connect('changed', self._on_driver_change)
        self.driver_dropdown_dialog = Gtk.ComboBoxText.new_with_entry()
        self.driver_dropdown_dialog.connect('changed', self._on_driver_change)
        self.driver_info_box = Gtk.HBox()
        self.driver_info_box_dialog = Gtk.HBox()
        self.driver_drone_box = Gtk.VBox(spacing=6)
        self.driver_drone_dialog = Gtk.VBox(spacing=6)
        self.game_dropdown = Gtk.ComboBoxText.new_with_entry()
        self.game_dropdown.connect('changed', self._on_game_change)
        self.game_dropdown_dialog = Gtk.ComboBoxText.new_with_entry()
        self.game_dropdown_dialog.connect('changed', self._on_game_change)
        self.game_box = Gtk.VBox(spacing=6)
        self.game_box_dialog = Gtk.VBox(spacing=6)
        self.race_dropdown = Gtk.ComboBoxText()
        self.race_dropdown.connect('changed', self._on_race_change)
        self.race_box = Gtk.VBox(spacing=6)
        
        # Éléments se modifiant durant une course (attention au multithreading)
        self.label_warmup = Gtk.Label()
        self.label_font = self.label_warmup.get_pango_context().get_font_description()
        self.update_box = Gtk.ListStore(
                int, str, str, int, int, int, str, str, str, str, str, str)
        self.button_box = Gtk.HBox()
        self.countdown = None
        self.timer = 0
        self.race_id = None

        # Contenu
        self.main = Gtk.Stack()
        self.main.set_margin_top(10)
        self.main.set_margin_bottom(10)
        self.main.set_margin_right(10)
        self.main.set_margin_left(10)
        self.main.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.main.set_transition_duration(700)
        self.main.set_homogeneous(True)
        self.add(self.main)

        self.main.add_named(
                Gtk.Image.new_from_file('resources/img/home.jpg'), 'default')
        self.main.add_named(self.create_event(), 'opened')
        self.main.add_named(self.create_loaded(), 'loaded')
        self.main.add_named(self.create_register(), 'register')
        self.main.add_named(self.create_race_manager(), 'race')
        self.main.add_named(self.create_game_manager(), 'game')
        self.main.add_named(self.create_launch_race(), 'launch')

        self._create_popup_dialog('registration',
                'Gestion des pilotes et des drones', self.create_register)
        self._create_popup_dialog('game',
                'Aménagement de l’aire de jeu', self.create_game_manager)

    ###                                                           ###
    #                                                               #
    # Création et activation des différentes parties de l’interface #
    #                                                               #
    ###                                                           ###
    def _create_popup_dialog(self, attr, title, generate_content):
        dialog = Gtk.Dialog(title, self, Gtk.DialogFlags.MODAL)
        dialog.get_content_area().add(generate_content(dialog.response))
        setattr(self, attr+'_dialog', dialog)

    def activate_default(self, *widget):
        self.set_custom_title('Bienvenue')
        self.main.set_visible_child_name('default')

    def create_event(self):
        panel = Gtk.VBox(spacing=6)
        label = Gtk.Label()
        label.set_markup('<b><big>Sélectionnez ou créez un évènement</big></b>')
        panel.pack_start(label, True, False, 4)
        row = Gtk.HBox()
        row.pack_start(Gtk.Label('Évènement'), False, False, 4)
        row.pack_start(self.event_dropdown, True, True, 4)
        panel.pack_start(row, True, False, 4)
        row = Gtk.HBox()
        label = Gtk.Label('Nombre de portes disponibles')
        row.pack_start(label, False, False, 4)
        row.pack_start(self.event_entry, True, True, 4)
        panel.pack_start(row, True, False, 4)
        def clear_entries(widget):
            self.event_dropdown.set_active(-1)
            self.event_dropdown.get_child().set_text('')
            self.activate_default()
        def check_entries(widget):
            try:
                nb_beacons = int(self.event_entry.get_text())
            except ValueError:
                dialog = WaitDialog(self,
                    'Erreur au chargement d’un évènement',
                    'La valeur renseignée pour le nombre de portes '
                    'disponibles n’est pas un entier.')
                dialog.run()
                dialog.destroy()
            else:
                if nb_beacons < 1:
                    dialog = WaitDialog(self,
                            'Erreur au chargement d’un évènement',
                            'Aucune porte disponible pour cet évènement.')
                    dialog.run()
                    dialog.destroy()
                    return
                event = self.event_dropdown.get_active_text()
                self.beacon_names = self.db.load_event(event, nb_beacons)
                self.event_dropdown.set_active(-1)
                self.event_dropdown.get_child().set_text('')
                self.activate_loaded()
                self._load_dropdown_values()
        row = Gtk.HBox()
        buttons_setup = (
            ('Ouvrir', 'document-open', check_entries),
            ('Annuler', 'window-close', clear_entries),
        )
        for text,name,callback in buttons_setup:
            button = Gtk.Button(label=text, image=Gtk.Image(icon_name=name))
            button.set_always_show_image(True)
            button.connect('clicked', callback)
            row.pack_end(button, False, False, 4)
        panel.pack_end(row, True, False, 4)
        return panel

    def activate_event(self, *wigdet):
        self.set_custom_title('Sélection d’un évènement')
        self.main.set_visible_child_name('opened')

    def create_loaded(self):
        panel = Gtk.VBox(spacing=6)
        button = Gtk.Button('Gestion des inscriptions de pilotes et de drones')
        button.connect('clicked', self.activate_register)
        panel.pack_start(child=button, expand=True, fill=True, padding=4)
        button = Gtk.Button(label='Mise en place et édition de parcours')
        button.connect('clicked', self.activate_game_manager)
        panel.pack_start(child=button, expand=True, fill=True, padding=4)
        button = Gtk.Button(label='Création et gestion de courses')
        button.connect('clicked', self.activate_race_manager)
        panel.pack_start(child=button, expand=True, fill=True, padding=4)
        return panel

    def activate_loaded(self, *widgets):
        self.set_custom_title('Menu principal')
        self.main.set_visible_child_name('loaded')

    def create_register(self, dialog_response=None):
        if dialog_response:
            dropdown = self.driver_dropdown_dialog
            info = self.driver_info_box_dialog
            box = self.driver_drone_dialog
        else:
            dropdown = self.driver_dropdown
            info = self.driver_info_box
            box = self.driver_drone_box
        entries = [Gtk.Entry() for _ in range(2)]
        labels = ['Numéro de téléphone', 'Adresse e-mail']
        panel = Gtk.VBox(spacing=6)
        row = Gtk.HBox()
        row.pack_start(Gtk.Label('Pilote'), False, False, 4)
        row.pack_start(dropdown, True, True, 4)
        panel.pack_start(row, True, False, 4)
        for label, entry in zip(labels, entries):
            info.pack_start(Gtk.Label(label), False, False, 4)
            info.pack_start(entry, True, True, 4)
        panel.pack_start(info, True, False, 4)
        panel.pack_start(box, True, False, 4)
        def clear_entries(widget):
            self.driver_dropdown.set_active(-1)
            self.driver_dropdown_dialog.set_active(-1)
            self.driver_dropdown.get_child().set_text('')
            self.driver_dropdown_dialog.get_child().set_text('')
            if dialog_response:
                dialog_response(0)
            else:
                self.activate_loaded()
        def check_entries(widget):
            maj = dropdown.get_active() > -1
            action = 'la mise à jour' if maj else 'l’inscription'
            driver_name = dropdown.get_active_text()
            if not driver_name:
                dialog = WaitDialog(self, 'Erreur à %s' % action,
                        'Le nom du pilote n’est pas renseigné.')
                dialog.run()
                dialog.destroy()
                return
            texts = [entry.get_text() for entry in entries]
            if '' in texts:
                dialog = WaitDialog(self, 'Erreur à %s' % action,
                        'Un numéro de téléphone et une adresse '
                        'e-mail sont nécessaires.')
                dialog.run()
                dialog.destroy()
                return
            if self.db.register_driver(driver_name, *texts):
                self.driver_dropdown.append_text(driver_name)
                self.driver_dropdown_dialog.append_text(driver_name)
            drones = dict((lambda w:
                (w[1].get_active_text(),w[3].get_text()))(
                    row.get_children()) for row in box.get_children())
            cleaned_drones = {}
            while len(drones):
                drone, category = drones.popitem()
                if drone and drone not in drones:
                    cleaned_drones[drone] = category
            self.db.register_drones_for_driver(driver_name,
                    *cleaned_drones.items())
            self._on_race_change(self.race_dropdown)
            clear_entries(widget)
        row = Gtk.HBox()
        buttons_setup = (
            ('Enregistrer', 'document-save', check_entries),
            ('Annuler', 'window-close', clear_entries),
        )
        for text, name, callback in buttons_setup:
            button = Gtk.Button(label=text, image=Gtk.Image(icon_name=name))
            button.set_always_show_image(True)
            button.connect('clicked', callback)
            row.pack_end(button, False, False, 4)
        panel.pack_end(row, True, False, 4)
        return panel

    def activate_register(self, *widget):
        self.set_custom_title('Gestion des pilotes et des drones')
        self.main.set_visible_child_name('register')

    def create_game_manager(self, dialog_response=None):
        if dialog_response:
            dropdown = self.game_dropdown_dialog
            box = self.game_box_dialog
        else:
            dropdown = self.game_dropdown
            box = self.game_box
        panel = Gtk.VBox(spacing=6)
        row = Gtk.HBox()
        row.pack_start(Gtk.Label('Nom du jeu'), False, False, 4)
        row.pack_start(dropdown, True, True, 4)
        panel.pack_start(row, True, False, 4)
        row = Gtk.HBox()
        row.pack_start(Gtk.Label('Nombre maximum de pilotes'), False, False, 4)
        nb_drivers = Gtk.Entry()
        row.pack_start(nb_drivers, True, True, 4)
        row.pack_start(Gtk.Label('Circuit ordonné'), False, False, 4)
        enforce_order = Gtk.Switch(state=False)
        row.pack_start(enforce_order, False, False, 4)
        panel.pack_start(row, True, False, 4)
        row = Gtk.HBox()
        row.pack_start(Gtk.Label('Secondes disponibles'), False, False, 4)
        time = Gtk.Entry()
        row.pack_start(time, True, True, 4)
        strict = Gtk.CheckButton(label='strict', active=True, sensitive=False)
        row.pack_start(strict, False, False, 4)
        row.pack_start(Gtk.Label('Nombre de tour à réaliser'), False, False, 4)
        laps = Gtk.Entry()
        row.pack_start(laps, True, True, 4)
        panel.pack_start(row, True, False, 4)
        panel.pack_start(box, True, False, 4)
        def enforce_strict(widget, gparam):
            if widget.get_active():
                strict.set_sensitive(True)
            else:
                strict.set_active(True)
                strict.set_sensitive(False)
        enforce_order.connect("notify::active", enforce_strict)
        def clear_entries(widget):
            self.game_box.foreach(lambda row: row.destroy())
            self.game_box_dialog.foreach(lambda row: row.destroy())
            self.game_dropdown.set_active(-1)
            self.game_dropdown_dialog.set_active(-1)
            self.game_dropdown.get_child().set_text('')
            self.game_dropdown_dialog.get_child().set_text('')
            nb_drivers.set_text('')
            enforce_order.set_active(False)
            time.set_text('')
            laps.set_text('')
            if dialog_response:
                dialog_response(0)
            else:
                self.activate_loaded()
        def check_entries(widget):
            game_name = self.game_dropdown_dialog.get_active_text() if\
                    dialog_response else self.game_dropdown.get_active_text()
            if not game_name:
                dialog = WaitDialog(self,
                        'Erreur à la création d’un type de jeu',
                        'Aucun nom n’a été spécifié pour ce jeu')
                dialog.run()
                dialog.destroy()
                return
            try:
                nb_drones = int(nb_driver.get_text() or '0')
                race_time = int(time.get_text() or '0')
                race_laps = int(laps.get_text() or '0')
            except ValueError:
                dialog = WaitDialog(self,
                        'Erreur à la création d’un type de jeu',
                        'La valeur renseignée pour le nombre maximal '
                        'de drones, le temps disponible ou le nombre '
                        'de tours à réaliser n’est pas un entier.')
                dialog.run()
                dialog.destroy()
                return
            if nb_drones < 1:
                dialog = WaitDialog(self,
                        'Erreur à la création d’un type de jeu',
                        'Aucun drone ne peut participer pour ce jeu.')
                dialog.run()
                dialog.destroy()
                return
            beacons = []
            rows = self.game_box_dialog.get_children() if\
                    dialog_response else self.game_box.get_children()
            for row in rows:
                _, porte, _, tpe, _, val, _, suiv, _ = row.get_children()
                porte = porte.get_active_text()
                if porte:
                    try:
                        val = int(val.get_text())
                    except ValueError:
                        dialog = WaitDialog(self,
                                'Erreur à la création d’un type de jeu',
                                'La valeur renseignée pour les points de la '
                                'porte {} n’est pas un entier.'.format(porte))
                        dialog.run()
                        dialog.destroy()
                        return
                    else:
                        beacons.append((
                            porte,
                            tpe.get_active(),
                            val,
                            suiv.get_active_text(),
                        ))
            free_fly = not enforce_order.get_active()
            is_strict = strict.get_active()
            try:
                rules_type = FreeForAll if free_fly else Rules
                rules_type(race_time, race_laps, beacons)
            except ConsoleError as e:
                dialog = WaitDialog(self,
                        'Erreur à la création d’un type de jeu',
                        e.args[0])
                dialog.run()
                dialog.destroy()
                return
            try:
                created = self.db.register_game(
                        game_name, nb_drones, race_time,
                        race_laps, free_fly, is_strict, beacons)
            except SQLError as e:
                dialog = WaitDialog(self,
                        'Erreur à la création d’un type de jeu',
                        e.args[0])
                dialog.run()
                dialog.destroy()
                return
            else:
                if created:
                    self.game_dropdown.append_text(game_name)
                    self.game_dropdown_dialog.append_text(game_name)
                    self.race_dropdown.append_text(game_name)
                clear_entries(widget)
        row = Gtk.HBox()
        buttons_setup = (
            ('Enregistrer', 'document-save', check_entries),
            ('Annuler', 'window-close', clear_entries),
        )
        for text, name, callback in buttons_setup:
            button = Gtk.Button(label=text, image=Gtk.Image(icon_name=name))
            button.set_always_show_image(True)
            button.connect('clicked', callback)
            row.pack_end(button, False, False, 4)
        panel.pack_end(row, True, False, 4)
        return panel

    def activate_game_manager(self, *widget):
        self.set_custom_title('Mise en place de parcours')
        self.main.set_visible_child_name('game')

    def create_race_manager(self):
        panel = Gtk.VBox(spacing=6)
        row = Gtk.HBox()
        row.pack_start(Gtk.Label('Type de jeu'), False, False, 4)
        row.pack_start(self.race_dropdown, True, True, 4)
        panel.pack_start(row, True, False, 4)
        panel.pack_start(self.race_box, True, False, 4)
        def clear_entries(widget):
            self.race_dropdown.set_active(-1)
            self.activate_loaded()
        def check_entries(widget):
            if self.race_dropdown.get_active() < 0:
                dialog = WaitDialog(self,
                        'Erreur à la création d’une course',
                        'Le type de jeu n’est pas défini')
                dialog.run()
                dialog.destroy()
                return
            entrants = []
            for row in self.race_box.get_children():
                _, driver, _, drone, _ = row.get_children()
                driver = driver.get_active_text()
                drone = drone.get_active_text()
                if not driver:
                    continue
                if not drone:
                    dialog = WaitDialog(self,
                            'Erreur à la création d’une course',
                            'Aucun drone sélectionné pour {}'.format(driver))
                    dialog.run()
                    dialog.destroy()
                    return
                if (driver, drone) in entrants:
                    dialog = WaitDialog(self,
                            'Erreur à la création d’une course',
                            '{} ne peut pas participer deux fois '
                            'sur cette course'.format(driver))
                    dialog.run()
                    dialog.destroy()
                    return
                entrants.append((driver, drone))
            if entrants:
                try:
                    game_name = self.race_dropdown.get_active_text()
                    _, race_time, race_laps, free_fly, strict, beacons =\
                            self.db.get_game_settings(game_name)
                    rules_type = FreeForAll if free_fly else Rules
                    rules = rules_type(race_time, race_laps, beacons)
                except ConsoleError as e:
                    dialog = WaitDialog(self,
                            'Erreur à la création d’une course',
                            e.args[0])
                    dialog.run()
                    dialog.destroy()
                else:
                    race_id = self.db.register_new_race(game_name, entrants)
                    self.console.setup_race(len(entrants), rules)
                    self.race_dropdown.set_active(-1)
                    self.activate_launch_race(race_id)
                    ordered_drivers = self.db.get_race_drivers(race_id)
                    rest.setup(game_name, rules, *ordered_drivers)
            else:
                dialog = WaitDialog(self,
                        'Erreur à la création d’une course',
                        'Aucun participant enregistré')
                dialog.run()
                dialog.destroy()
        row = Gtk.HBox()
        buttons_setup = (
            ('Valider', 'system-run', check_entries),
            ('Annuler', 'window-close', clear_entries),
        )
        for text, name, callback in buttons_setup:
            button = Gtk.Button(label=text, image=Gtk.Image(icon_name=name))
            button.set_always_show_image(True)
            button.connect('clicked', callback)
            row.pack_end(button, False, False, 4)
        panel.pack_end(row, True, False, 4)
        return panel

    def activate_race_manager(self, *widget):
        if self.race_id is not None:
            self.activate_launch_race()
        else:
            self.set_custom_title('Mise en place d’une course')
            self.main.set_visible_child_name('race')

    def create_launch_race(self):
        panel = Gtk.VBox(spacing=6)
        panel.pack_start(self.label_warmup, True, False, 4)
        treeview = Gtk.TreeView(model=self.update_box)
        titles = [
            'Balise',
            'Pilote',
            'Drone',
            'Place',
            'Points',
            'Tours',
            'Temps',
            'Retard',
            'Dernier tour',
            'Porte',
        ]
        for i, title in enumerate(titles):
            renderer = Gtk.CellRendererText(xalign=0.5)
            column = Gtk.TreeViewColumn(title, renderer, text=i)
            column.set_alignment(0.5)
            column.set_sort_column_id(i)
            column.set_expand(i in (1,2))
            treeview.append_column(column)
        index = len(titles)
        renderer = Gtk.CellRendererText(xalign=0.5)
        renderer.props.font_desc = Pango.FontDescription('FontAwesome')
        column = Gtk.TreeViewColumn('Status', renderer, text=index)
        column.set_alignment(0.5)
        column.set_sort_column_id(index)
        treeview.append_column(column)
        index += 1
        renderer = Gtk.CellRendererText(xalign=0.5)
        renderer.props.editable = True
        column = Gtk.TreeViewColumn('Juge', renderer, text=index)
        column.set_alignment(0.5)
        treeview.append_column(column)
        renderer.connect('edited', self._on_judge_edition)
        panel.pack_start(treeview, True, True, 4)
        def cancel_race(widget):
            drones = len(self.console.scores)
            self.console.cancel_race()
            self.db.update_race(self.race_id, *self.console.scores)
            self.button_box.get_children()[3].set_sensitive(True)
            self.race_id = None
            self.label_warmup.modify_font(self.label_font)
            self.activate_loaded()
        def close_race(widget):
            self.race_id = None
            self.label_warmup.modify_font(self.label_font)
            rest.leaderboard(*self.console.scores)
            self.activate_loaded()
        def stop_race(widget):
            widget.hide()
            self.console.stop_race()
            self.db.update_race(self.race_id, *self.console.scores)
            cancel, close = self.button_box.get_children()[1:3]
            cancel.hide()
            close.show_all()
        def launch_race(widget):
            widget.hide()
            self.countdown = 4
            cancel, stop = self.button_box.get_children()[1:4:2]
            cancel.set_sensitive(False)
            stop.set_sensitive(False)
            stop.show_all()
            self.label_warmup.set_text('')
            self.label_warmup.modify_font(Pango.FontDescription('40'))
            GLib.timeout_add_seconds(1, self.show_countdown)
        buttons_setup = (
            ('Démarrer', 'media-playback-start', launch_race),
            ('Arrêter', 'media-playback-pause', stop_race),
            ('Clore', 'application-exit', close_race),
            ('Annuler', 'window-close', cancel_race),
            ('Retour au menu', 'go-home', self.activate_loaded),
        )
        for text, name, callback in buttons_setup:
            button = Gtk.Button(label=text, image=Gtk.Image(icon_name=name))
            button.set_always_show_image(True)
            button.connect('clicked', callback)
            self.button_box.pack_end(button, False, False, 4)
        panel.pack_end(self.button_box, True, False, 4)
        return panel

    def activate_launch_race(self, race_id=None):
        self.set_custom_title('Monitoring d’une course')
        self.main.set_visible_child_name('launch')
        if race_id is not None:
            self.race_id = race_id
            self.label_warmup.set_text('Chaque pilote doit recevoir '
                    'la balise correspondant à son numéro')
            self.update_box.clear()
            for i, driver, drone in self.db.get_race_drivers(race_id):
                self.update_box.append([
                    i, driver, drone, 1, 0, 0, '00:00.0',
                    '00:00.0', '-', '-', '\uf018', ''])
            self.button_box.show_all()
            # Cache le bouton arrêter et le bouton clore
            self.button_box.get_children()[2].hide()
            self.button_box.get_children()[3].hide()

    ###                                                    ###
    #                                                        #
    # Création différentes boites de dialogue pour les menus #
    #                                                        #
    ###                                                    ###
    def create_manage_categories(self):
        panel = Gtk.VBox(spacing=6)
        row = Gtk.HBox()
        row.pack_start(Gtk.Label('Drone'), False, False, 4)
        dropdown = Gtk.ComboBoxText()
        for drone in self.db.get_drones():
            dropdown.append_text(drone)
        row.pack_start(dropdown, True, True, 4)
        panel.pack_start(row, True, False, 4)
        row = Gtk.HBox()
        row.pack_start(Gtk.Label('Catégorie'), False, False, 4)
        entry = Gtk.ComboBoxText.new_with_entry()
        for category in self.db.get_categories():
            if category:
                entry.append_text(category)
        row.pack_start(entry, True, True, 4)
        panel.pack_start(row, True, False, 4)
        def update(widget):
            if dropdown.get_active() > -1:
                self.db.set_category_for_drone(
                        dropdown.get_active_text(),
                        widget.get_active_text())
        entry.connect('changed', update)
        def load(widget):
            if widget.get_active() > -1:
                entry.get_child().set_text(self.db.get_category_for_drone(
                    widget.get_active_text()))
        dropdown.connect('changed', load)
        return panel

    ###                          ###
    #                              #
    # Gestion de la base de donnée #
    #                              #
    ###                          ###
    def new_database(self, *extra_args):
        self._load_database(
            'Créer une nouvelle base de donnée',
            Gtk.FileChooserAction.SAVE,
            'Enregistrer', 'document-save', sql_create)

    def open_database(self, *extra_args):
        self._load_database(
            'Sélectionnez la base de donnée à ouvrir',
            Gtk.FileChooserAction.OPEN,
            'Ouvrir', 'document-open', sql_open)

    def _load_database(self, title, action, dialog_ok, icon, sql_generate):
        dialog = Gtk.FileChooserDialog(title, self, action)
        button = dialog.add_button('Annuler', Gtk.ResponseType.CANCEL)
        button.set_image(Gtk.Image(icon_name='window-close'))
        button.set_always_show_image(True)
        button = dialog.add_button(dialog_ok, Gtk.ResponseType.OK)
        button.set_image(Gtk.Image(icon_name=icon))
        button.set_always_show_image(True)
        response = dialog.run()
        filename = dialog.get_filename()
        dialog.destroy()
        if response != Gtk.ResponseType.OK:
            return
        self.close_database()
        try:
            self.db = sql_generate(filename)
        except SQLError as e:
            dialog = WaitDialog(self, 'Une erreur est survenue', e.args[0])
            dialog.run()
            dialog.destroy()
            self.db = None
        else:
            self.event_dropdown.set_active(-1)
            self.event_dropdown.get_child().set_text('')
            self.event_dropdown.remove_all()
            for event in self.db.get_events():
                self.event_dropdown.append_text(event)
            self.activate_event()

    def close_database(self, *widgets):
        try:
            self.console.stop_race()
        except ConsoleError:
            pass
        if self.db:
            self.db.close()
            self.db = None
        self.beacon_names = None
        self.activate_default()
        self._clear_dropdown_values()

    ###                                            ###
    #                                                #
    # Machine à état, chargement et purge de données #
    #                                                #
    ###                                            ###
    def _load_dropdown_values(self):
        self.driver_dropdown.set_active(-1)
        self.driver_dropdown_dialog.set_active(-1)
        for driver in self.db.get_drivers():
            self.driver_dropdown.append_text(driver)
            self.driver_dropdown_dialog.append_text(driver)
        self.game_dropdown.set_active(-1)
        self.game_dropdown_dialog.set_active(-1)
        self.race_dropdown.set_active(-1)
        for game in self.db.get_game_names():
            self.game_dropdown.append_text(game)
            self.game_dropdown_dialog.append_text(game)
            self.race_dropdown.append_text(game)
        self._add_beacon_row()

    def _clear_dropdown_values(self):
        self.driver_dropdown.set_active(-1)
        self.driver_dropdown_dialog.set_active(-1)
        self.driver_dropdown.remove_all()
        self.driver_dropdown_dialog.remove_all()
        # not cleared automatically on 'changed' signal
        self.game_box.foreach(lambda widget: widget.destroy())
        self.game_box_dialog.foreach(lambda widget: widget.destroy())
        self.game_dropdown.set_active(-1)
        self.game_dropdown.remove_all()
        self.game_dropdown_dialog.set_active(-1)
        self.game_dropdown_dialog.remove_all()
        self.race_dropdown.set_active(-1)
        self.race_dropdown.remove_all()

    ###                            ###
    #                                #
    # Gestion des différents signaux #
    #                                #
    ###                            ###
    def _on_event_selected(self, widget):
        if widget.get_active() > -1:
            nb_beacons = self.db.get_event_settings(widget.get_active_text())
            self.event_entry.set_text(str(nb_beacons))
            self.event_entry.set_editable(False)
        else:
            self.event_entry.set_text('')
            self.event_entry.set_editable(True)

    def _on_driver_change(self, widget):
        active_id = widget.get_active()
        if self.driver_dropdown.get_active() != active_id:
            self.driver_dropdown.set_active(active_id)
            return
        if self.driver_dropdown_dialog.get_active() != active_id:
            self.driver_dropdown_dialog.set_active(active_id)
            return
        self.driver_drone_box.foreach(lambda widget: widget.destroy())
        self.driver_drone_dialog.foreach(lambda widget: widget.destroy())
        for info in (self.driver_info_box, self.driver_info_box_dialog):
            _, e1, _, e2 = info.get_children()
            e1.set_text('')
            e2.set_text('')
        if active_id > -1:
            # Normalement, les deux dropdown ont le même texte
            driver = widget.get_active_text()
            phone, mail = self.db.get_driver_info(driver)
            for info in (self.driver_info_box, self.driver_info_box_dialog):
                _, e1, _, e2 = info.get_children()
                e1.set_text(phone)
                e2.set_text(mail)
            drones = self.db.get_drones_for(driver)
            for drone in drones:
                self._add_driver_drone_row(drone=drone)
        self._add_driver_drone_row()

    def _add_driver_drone_row(self, widget=None, drone=None):
        if widget:
            if widget.get_active() > -1:
                entry = widget.get_parent().get_children()[-1]
                entry.set_text(self.db.get_category_for_drone(
                    widget.get_active_text()))
            widget.disconnect_by_func(self._add_driver_drone_row)
        for panel in (self.driver_drone_box, self.driver_drone_dialog):
            row = Gtk.HBox()
            row.pack_start(Gtk.Label('Type de drone'), False, False, 4)
            drones = self.db.get_drones()
            dropdown = Gtk.ComboBoxText.new_with_entry()
            for d in drones:
                dropdown.append_text(d)
            row.pack_start(dropdown, True, True, 4)
            row.pack_start(Gtk.Label('Catégorie'), False, False, 4)
            entry = Gtk.Entry()
            row.pack_start(entry, True, True, 4)
            panel.pack_start(row, True, False, 4)
            if drone is None:
                dropdown.connect('changed', self._add_driver_drone_row)
            else:
                dropdown.get_child().set_text(drone)
                entry.set_text(self.db.get_category_for_drone(drone))
            panel.show_all()

    def _on_game_change(self, widget):
        active_id = widget.get_active()
        if self.game_dropdown.get_active() != active_id:
            self.game_dropdown.set_active(active_id)
            return
        if self.game_dropdown_dialog.get_active() != active_id:
            self.game_dropdown_dialog.set_active(active_id)
            return
        if active_id > -1:
            self.game_box.foreach(lambda row: row.destroy())
            self.game_box_dialog.foreach(lambda row: row.destroy())
            # Normalement, les deux dropdown ont le même texte
            game_name = widget.get_active_text()
            drones, time, laps, free, strict, registered_beacons =\
                    self.db.get_game_settings(game_name)
            row1, row2 = self.game_box.get_parent().get_parent(
                    ).get_children()[1:3]
            drone, enforce = row1.get_children()[1:4:2]
            drone.set_text(str(drones))
            enforce.set_active(not free)
            time_box, strict_box, _, laps_box = row2.get_children()[1:5]
            time_box.set_text(str(time))
            strict_box.set_state(strict)
            laps_box.set_text(str(laps))
            row1, row2 = self.game_box_dialog.get_parent().get_parent(
                    ).get_children()[1:3]
            drone, enforce = row1.get_children()[1:4:2]
            drone.set_text(str(drones))
            enforce.set_active(not free)
            time_box, strict_box, _, laps_box = row2.get_children()[1:5]
            time_box.set_text(str(time))
            strict_box.set_state(strict)
            laps_box.set_text(str(laps))
            self._add_beacon_row()
            for b, t, v, n in registered_beacons:
                current = self.beacon_names.index(b)
                next_one = self.beacon_names.index(n)
                points = str(v)
                row = self.game_box.get_children()[-1]
                _, bb, _, tt, _, vv, _, nn, _ = row.get_children()
                bb.set_active(current)
                tt.set_active(t)
                vv.set_text(points)
                nn.set_active(next_one)
                row = self.game_box_dialog.get_children()[-1]
                _, bb, _, tt, _, vv, _, nn, _ = row.get_children()
                bb.set_active(current)
                tt.set_active(t)
                vv.set_text(points)
                nn.set_active(next_one)
        elif not (len(self.game_box.get_children()) and
                len(self.game_box_dialog.get_children())):
            self._add_beacon_row()

    def _add_beacon_row(self, widget=None):
        widget_parent = (self.game_box, self.game_box_dialog)
        if widget:
            widget.disconnect_by_func(self._add_beacon_row)
            if widget.get_parent().get_parent() is self.game_box:
                widget_parent = (self.game_box,)
            else:
                widget_parent = (self.game_box_dialog,)
        for panel in widget_parent:
            row = Gtk.HBox()
            row.pack_start(Gtk.Label('Porte'), False, False, 4)
            dropdown = Gtk.ComboBoxText()
            for name in self.beacon_names:
                dropdown.append_text(name)
            dropdown.connect('changed', self._add_beacon_row)
            row.pack_start(dropdown, False, False, 4)
            row.pack_start(Gtk.Label('Type'), False, False, 4)
            dropdown = Gtk.ComboBoxText()
            for beacon in Beacons:
                dropdown.append_text(beacon.description)
            label = Gtk.Label('**aucun type défini**')
            dropdown.connect('changed', lambda d: label.set_text(
                'Multiplicateur' if Beacons(d.get_active()).is_time
                else 'Nombre de points'))
            dropdown.set_active(4)
            row.pack_start(dropdown, False, False, 4)
            row.pack_start(label, False, False, 4)
            row.pack_start(Gtk.Entry(), True, True, 4)
            row.pack_start(Gtk.Label('Porte suivante'), False, False, 4)
            dropdown = Gtk.ComboBoxText()
            for name in self.beacon_names:
                dropdown.append_text(name)
            row.pack_start(dropdown, False, False, 4)
            button = Gtk.Button(image=Gtk.Image(icon_name='window-close'))
            button.connect('clicked',
                    lambda w: row.destroy() or (self._add_beacon_row()
                        if not len(panel.get_children()) else None))
            row.pack_start(button, False, False, 4)
            panel.pack_start(row, True, False, 4)
            panel.show_all()

    def _on_race_change(self, widget):
        self.race_box.foreach(lambda w: w.destroy())
        if widget.get_active() > -1:
            game_name = widget.get_active_text()
            count, *_ = self.db.get_game_settings(game_name)
            dropdown_drivers = [Gtk.ComboBoxText() for _ in range(count)]
            dropdown_drones = [Gtk.ComboBoxText() for _ in range(count)]
            def clear_driver(driver):
                def _callback(widget):
                    driver.set_active(-1)
                return _callback
            drivers = self.db.get_drivers()
            for driver in drivers:
                for dropdown in dropdown_drivers:
                    dropdown.append_text(driver)
            for idx in range(count):
                row = Gtk.HBox()
                row.pack_start(Gtk.Label('Pilote'), False, False, 4)
                driver = dropdown_drivers[idx]
                row.pack_start(driver, True, True, 4)
                row.pack_start(Gtk.Label('sur drone'), False, False, 4)
                drone = dropdown_drones[idx]
                drone.append_text('---------')
                drone.remove_all()
                row.pack_start(drone, True, True, 4)
                button = Gtk.Button(image=Gtk.Image(icon_name='window-close'))
                button.connect('clicked', clear_driver(driver))
                row.pack_start(button, False, False, 4)
                self.race_box.pack_start(row, True, False, 4)
            for driver, drone in zip(dropdown_drivers, dropdown_drones):
                driver.connect('changed', self._on_race_new_driver(drone))
            self.race_box.show_all()

    def _on_race_new_driver(self, drone_dropdown):
        def _callback(widget):
            drone_dropdown.remove_all()
            if widget.get_active() > -1:
                drones = self.db.get_drones_for(widget.get_active_text())
                for drone in drones:
                    drone_dropdown.append_text(drone)
        return _callback

    def _on_judge_edition(self, widget, path, text):
        if not text:
            return
        drone = self.update_box[path][0] - 1
        try:
            points = int(text)
        except ValueError:
            self.console.kill_drone(drone)
        else:
            self.console.edit_score(drone, points)

    ###                            ###
    #                                #
    # Gestion d’une course en direct #
    #                                #
    ###                            ###
    def show_countdown(self):
        self.countdown -= 1
        c = self.countdown
        text = str(c) if c else 'GO!'
        rest.warmup({'text': text, 'start': c == -1})
        if c >= 0:
            self.label_warmup.set_text(text)
            return True
        cancel_btn, stop_btn = self.button_box.get_children()[1:4:2]
        try:
            self.timer = 0
            self.console.start_race()
        except ConsoleError as e:
            dialog = WaitDialog(self, 'Une erreur est survenue', e.args[0])
            dialog.run()
            dialog.destroy()
        else:
            stop_btn.set_sensitive(True)
            GLib.timeout_add(100, self.show_timer)
        finally:
            cancel_btn.set_sensitive(True)
            self.countdown = None
        return False

    def show_timer(self):
        self.timer += 1
        mins, secs = divmod(self.timer, 600)
        self.label_warmup.set_text('{:02d}:{:04.1f}'.format(mins, secs/10))
        if self.console.extra_data:
            return True
        cancel_btn, close_btn, stop_btn = self.button_box.get_children()[1:4]
        cancel_btn.hide()
        stop_btn.hide()
        close_btn.show_all()
        return False

    def get_time(self):
        return self.timer

    def update_race(self, status):
        GLib.idle_add(
                self._grid_update, status['id'] - 1,
                status['position'], status['points'],
                status['tours'], status['temps'],
                status['retard'], status['tour'],
                status['porte'], status['finish'])

    def _grid_update(self, i, pos, pts, laps, time, delay, last, beacon, end):
        treeiter = self.update_box.get_iter(Gtk.TreePath(i))
        row = self.update_box[treeiter]
        row[3] = pos
        row[4] = pts
        row[5] = laps
        row[6] = '{:02.0f}:{:04.1f}'.format(*divmod(time, 60))
        row[7] = '{:02.0f}:{:04.1f}'.format(*divmod(delay, 60))
        if last:
            row[8] = '{:02.0f}:{:04.1f}'.format(*divmod(last, 60))
        if beacon:
            row[9] = beacon
        row[10] = '\uf1d9' if end is None else end and '\uf11e' or '\uf0f9'

    ###                              ###
    #                                  #
    # Coup de balai après la fermeture #
    #                                  #
    ###                              ###
    def shutdown(self, *args):
        if self.db:
            self.db.close()
        rest.cancel()
        self.reader_thread.should_continue = False
        print('Drone Racer successfully shut down')
