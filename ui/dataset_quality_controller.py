"""Connect Data Insight quality reports to training and split cleanup."""
from PySide6.QtCore import QObject, QEvent, QThread, Signal, Slot, QCoreApplication
from PySide6.QtWidgets import QMessageBox
from core.dataset_quality import fingerprint, cleanup_plan, apply_cleanup, blocking_samples
from ui.widgets.ui_utils import create_flat_button


class QualityJob(QThread):
    done = Signal(object, object)

    def __init__(self, operation, parent):
        super().__init__(parent)
        self.operation = operation

    def run(self):
        try:
            self.done.emit(self.operation(), None)
        except Exception as exc:
            self.done.emit(None, exc)


class DatasetQualityController(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.panel = window.ui.analysis_panel
        self.card = window.ui.widget_healthCheck
        self.snapshot = None
        self.issues = {}
        self.job = None
        self.button = create_flat_button(text='', icon_name='fa5s.trash-alt',
                                         on_clicked=self.clean)
        layout = self.card.btn_export.parentWidget().layout()
        # Export is nested in the card toolbar's layout.
        def insert_after_export(layout):
            for i in range(layout.count()):
                item = layout.itemAt(i)
                if item.widget() is self.card.btn_export:
                    layout.insertWidget(i + 1, self.button)
                    return True
                if item.layout() and insert_after_export(item.layout()):
                    return True
            return False
        insert_after_export(self.card.layout())
        self.card.installEventFilter(self)
        self.translate()
        self.panel.analysis_started.connect(self.invalidate)
        self.panel.analysis_finished.connect(self.capture)
        # Connection to the regular training slot is installed later by MainWindow.
        window.ui.pushButton_run.clicked.connect(self.guard)

    def text(self, source):
        return QCoreApplication.translate('DatasetQuality', source)

    def translate(self):
        self.button.setText(self.text('Remove invalid samples'))
        self.button.setToolTip(self.text('Back up split lists and remove missing or unreadable samples. Original files are kept.'))

    def eventFilter(self, obj, event):
        if event.type() == QEvent.LanguageChange:
            self.translate()
        return False

    @Slot()
    def invalidate(self):
        self.snapshot = None

    def busy(self):
        thread = getattr(self.window, '_training_thread', None)
        return bool((self.job and self.job.isRunning()) or
                    (thread and thread.isRunning()) or
                    self.panel._current_state.name == 'RUNNING')

    def run_job(self, operation, callback):
        self.button.setEnabled(False)
        self.job = QualityJob(operation, self)
        def done(value, error):
            self.button.setEnabled(True)
            if error:
                QMessageBox.warning(self.window, self.text('Dataset quality'),
                                    self.text(str(error)))
            else:
                callback(value)
        self.job.done.connect(done)
        self.job.start()

    @Slot()
    def capture(self):
        root = self.window._current_data_root
        self.issues = self.panel.metadata_manager.get_health_check_issues() or {}
        from core.quality_cache import certify
        db_path = self.panel.metadata_manager.database.db_path
        self.run_job(lambda: (root, certify(db_path, root)), self.set_snapshot)

    def set_snapshot(self, value):
        self.snapshot = value

    @Slot()
    def guard(self):
        if self.busy():
            return
        root = getattr(self.window, '_current_data_root', '')
        if not self.snapshot or self.snapshot[0] != root:
            QMessageBox.warning(self.window, self.text('Dataset quality'),
                                self.text('Complete Data Insight quality checks before training.'))
            return
        def check():
            if fingerprint(root) != self.snapshot[1]:
                raise ValueError('Dataset changed. Run the quality check again.')
            bad = blocking_samples(root, self.issues)
            if bad:
                raise ValueError('Fatal dataset issues block training. Remove invalid samples or repair the files.')
        self.run_job(check, lambda _: self.window._on_start_training())

    @Slot()
    def clean(self):
        if self.busy() or not self.snapshot:
            return
        from core.quality_cache import certify, cleanup_cached
        root = self.window._current_data_root
        db_path = self.panel.metadata_manager.database.db_path
        def prepare():
            if not self.snapshot or root != self.snapshot[0]:
                raise ValueError('Dataset changed. Run the quality check again.')
            if fingerprint(root) != self.snapshot[1]:
                raise ValueError('Dataset changed. Run the quality check again.')
            return cleanup_plan(root, self.issues)
        self.run_job(prepare, self.confirm)

    def confirm(self, plan):
        if not plan:
            QMessageBox.information(self.window, self.text('Dataset quality'), self.text('No invalid samples to remove.'))
            return
        detail = '\n'.join(f'{p.name}: {n}' for p, _, _, n in plan)
        answer = QMessageBox.question(self.window, self.text('Remove invalid samples'),
            self.text('Back up split lists and remove missing or unreadable samples. Original files are kept.') + '\n\n' + detail,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer == QMessageBox.Yes:
            from core.quality_cache import cleanup_cached
            root, expected = self.snapshot
            db_path = self.panel.metadata_manager.database.db_path
            self.run_job(lambda: cleanup_cached(plan, db_path, root, expected), self.cleaned)

    def cleaned(self, backups):
        self.invalidate()
        root = self.window._current_data_root
        self.window.data_manager.load_from_txt_files(root)
        self.window._update_dataset_overview()
        # The pruned DB is certified: this reload uses the cache, not decoding.
        self.window._initialize_analysis_panel(root)
        QMessageBox.information(self.window, self.text('Dataset quality'),
            self.text('Lists updated. Backups:') + '\n' + '\n'.join(map(str, backups)))
