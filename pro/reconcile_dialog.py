# reconcile_dialog.py
import sqlite3
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QMessageBox, QAbstractItemView
)
from PyQt6.QtCore import Qt


class ReconcileDialog(QDialog):
    """
    Reconcile dialog for the cashbook table.

    Expects:
      parent: parent widget or None
      conn: sqlite3.Connection instance
      parent_tab: optional reference to the tab that opened this dialog (to call refresh)
    """

    def __init__(self, parent, conn: sqlite3.Connection, parent_tab=None):
        super().__init__(parent)
        self.setWindowTitle("Reconcile Cash Book")
        self.resize(900, 480)

        if not isinstance(conn, sqlite3.Connection):
            raise ValueError("conn must be an sqlite3.Connection")

        self.conn = conn
        self.parent_tab = parent_tab

        self._build_ui()
        self.load_open_entries()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        header = QLabel("Select entries to mark as reconciled (or select and Unreconcile).")
        layout.addWidget(header)

        # Table with entries
        self.table = QTableWidget()
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels([
            "id", "Date", "Account", "Reference", "Narration",
            "Debit", "Credit", "Amount", "Batch No", "Entry Type"
        ])
        # hide id column visually
        self.table.setColumnHidden(0, True)

        # selection behaviour
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        layout.addWidget(self.table)

        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_reconcile = QPushButton("Mark Selected as Reconciled")
        self.btn_unreconcile = QPushButton("Unreconcile Selected")
        self.btn_refresh = QPushButton("Refresh")
        self.btn_close = QPushButton("Close")

        btn_layout.addWidget(self.btn_reconcile)
        btn_layout.addWidget(self.btn_unreconcile)
        btn_layout.addWidget(self.btn_refresh)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

        # Connect signals (note: do NOT call methods here; pass the callable)
        self.btn_reconcile.clicked.connect(self.on_reconcile_selected)
        self.btn_unreconcile.clicked.connect(self.on_unreconcile_selected)
        self.btn_refresh.clicked.connect(self.load_open_entries)
        self.btn_close.clicked.connect(self.close)

    def load_open_entries(self):
        """
        Load all entries where reconciled is 0 (or NULL) and populate the table.
        """
        try:
            cur = self.conn.cursor()
            cur.execute("""
                SELECT
                    id,
                    date,
                    account,
                    reference,
                    narration,
                    IFNULL(debit, 0.0) AS debit,
                    IFNULL(credit, 0.0) AS credit,
                    batch_no,
                    entry_type
                FROM cash_book
                WHERE IFNULL(reconciled, 0) = 0
                ORDER BY date ASC, id ASC
            """)
            rows = cur.fetchall()
        except Exception as e:
            QMessageBox.critical(self, "Database error", f"Failed to load entries:\n{e}")
            return

        self.table.setRowCount(len(rows))

        for r_idx, row in enumerate(rows):
            # row layout corresponds to the SELECT order
            _id, date, account, reference, narration, debit, credit, batch_no, entry_type = row

            amount = (debit or 0.0) - (credit or 0.0)

            cells = [
                str(_id),
                str(date) if date is not None else "",
                str(account) if account is not None else "",
                str(reference) if reference is not None else "",
                str(narration) if narration is not None else "",
                f"{debit:.2f}" if isinstance(debit, (int, float)) else str(debit),
                f"{credit:.2f}" if isinstance(credit, (int, float)) else str(credit),
                f"{amount:.2f}",
                str(batch_no) if batch_no is not None else "",
                str(entry_type) if entry_type is not None else ""
            ]

            for c_idx, value in enumerate(cells):
                item = QTableWidgetItem(value)
                # numeric columns align right
                if c_idx in (5, 6, 7):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                # don't allow editing
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(r_idx, c_idx, item)

        # Resize columns to contents
        self.table.resizeColumnsToContents()
        # keep id column hidden
        self.table.setColumnHidden(0, True)

    def _get_selected_ids(self):
        """Return list of integer IDs for currently selected rows."""
        selected = self.table.selectionModel().selectedRows()
        ids = []
        for model_index in selected:
            row = model_index.row()
            id_item = self.table.item(row, 0)
            if id_item:
                try:
                    ids.append(int(id_item.text()))
                except ValueError:
                    continue
        return ids

    def on_reconcile_selected(self):
        """Mark selected rows reconciled (set reconciled = 1)."""
        ids = self._get_selected_ids()
        if not ids:
            QMessageBox.information(self, "No selection", "Please select one or more rows to reconcile.")
            return

        confirm = QMessageBox.question(
            self,
            "Confirm reconcile",
            f"Mark {len(ids)} selected entries as reconciled?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            cur = self.conn.cursor()
            # Begin transaction
            cur.execute("BEGIN")
            cur.executemany("UPDATE cash_book SET reconciled = 1 WHERE id = ?", [(i,) for i in ids])
            self.conn.commit()
        except Exception as e:
            try:
                self.conn.rollback()
            except Exception:
                pass
            QMessageBox.critical(self, "Database error", f"Failed to mark reconciled:\n{e}")
            return

        QMessageBox.information(self, "Done", f"{len(ids)} entries marked reconciled.")
        self.load_open_entries()
        self._notify_parent_refresh()

    def on_unreconcile_selected(self):
        """Set reconciled = 0 for selected rows (in case you want to undo)."""
        ids = self._get_selected_ids()
        if not ids:
            QMessageBox.information(self, "No selection", "Please select one or more rows to unreconcile.")
            return

        confirm = QMessageBox.question(
            self,
            "Confirm unreconcile",
            f"Mark {len(ids)} selected entries as unreconciled?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            cur = self.conn.cursor()
            cur.execute("BEGIN")
            cur.executemany("UPDATE cashbook SET reconciled = 0 WHERE id = ?", [(i,) for i in ids])
            self.conn.commit()
        except Exception as e:
            try:
                self.conn.rollback()
            except Exception:
                pass
            QMessageBox.critical(self, "Database error", f"Failed to update entries:\n{e}")
            return

        QMessageBox.information(self, "Done", f"{len(ids)} entries updated.")
        self.load_open_entries()
        self._notify_parent_refresh()

    def _notify_parent_refresh(self):
        """
        If the parent tab supplies a refresh() or load_transactions() method, call it to update UI.
        This is safe-guarded with hasattr checks.
        """
        if self.parent_tab is None:
            return

        try:
            if hasattr(self.parent_tab, "refresh"):
                self.parent_tab.refresh()
            elif hasattr(self.parent_tab, "load_transactions"):
                self.parent_tab.load_transactions()
            elif hasattr(self.parent_tab, "load_open_entries"):
                # some tabs may expose this
                self.parent_tab.load_open_entries()
        except Exception as e:
            # don't crash the dialog if parent refresh fails; just log
            print(f"[ReconcileDialog] Parent refresh failed: {e}")
