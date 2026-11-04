import sys
from functools import partial
from pathlib import Path
import math

try:
    from PySide6 import QtCore
    from PySide6 import QtGui
    from PySide6 import QtWidgets
except ImportError:
    from PySide2 import QtCore
    from PySide2 import QtGui
    from PySide2 import QtWidgets

from pipeline_utils.netcopy_abstract import NetCopy


class NetCopyDialog(QtWidgets.QDialog):
    FILE_FILTERS = "All Image Files (*.usd *.usda);;All Files (*.*)"
    selected_filter = "All Image Files (*.usd *.usda)"

    dlg_instance = None
    
    @classmethod
    def show_dialog(cls, netcopy: NetCopy, storage_path: Path):
        if not cls.dlg_instance:
            cls.dlg_instance = NetCopyDialog(netcopy, storage_path)

        if cls.dlg_instance.isHidden():
            cls.dlg_instance.show()
        else:
            cls.dlg_instance.raise_()
            cls.dlg_instance.activateWindow()

    def __init__(self, netcopy: NetCopy, storage_path: Path):
        """Initialise NetCopyDialog"""
        super().__init__(netcopy.get_main_window())

        self.netcopy = netcopy
        self.storage_path = storage_path
        self.setWindowTitle("NetCopy")

        size = netcopy.get_main_window().screen().size()
        screen_w, screen_h = size.width(), size.height()
        self.resize(int(screen_w * 0.25), int(screen_h * 0.4))

        self.page_input_width = int(screen_w * 0.035)
        
        self.copies = netcopy.get_all_copies(self.storage_path)
        self.filtered_copies = []
        self.page_num = 0

        self.create_widgets()
        self.create_layout()
        self.create_connections()

    def create_widgets(self):
        """Create all widgets for the UI"""
        self.send_le = QtWidgets.QLineEdit()
        self.send_btn = QtWidgets.QPushButton("Send Copy", default=False, autoDefault=False)

        self.filter_le = QtWidgets.QLineEdit()
        self.filter_btn = QtWidgets.QPushButton("Filter", default=False, autoDefault=False)

        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self.splitter.setChildrenCollapsible(False)

        self.copy_table = QtWidgets.QTableWidget(0, 3)
        self.copy_table.setHorizontalHeaderLabels(["Name", "Time", "Confirm"])
        self.copy_table.resizeColumnsToContents()
        self.copy_table.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.copy_table.setFocusPolicy(QtCore.Qt.NoFocus)
        
        self.page_left_btn = QtWidgets.QPushButton("<", default=False, autoDefault=False)
        self.page_left_btn.setFixedWidth(self.page_input_width * 0.4)

        self.page_le = QtWidgets.QLineEdit("1")
        self.page_le.setFixedWidth(self.page_input_width * 0.4)
        self.page_le.setValidator(QtGui.QIntValidator())

        self.page_right_btn = QtWidgets.QPushButton(">", default=False, autoDefault=False)
        self.page_right_btn.setFixedWidth(self.page_input_width * 0.4)

        self.refresh_btn = QtWidgets.QPushButton("Refresh")
        self.close_btn = QtWidgets.QPushButton("Close")

    def create_layout(self):
        """Create all layouts and add widgets to them"""
        send_copy_layout = QtWidgets.QHBoxLayout()
        send_copy_layout.addWidget(self.send_le)
        send_copy_layout.addWidget(self.send_btn)

        filter_layout = QtWidgets.QHBoxLayout()
        filter_layout.addWidget(self.filter_le)
        filter_layout.addWidget(self.filter_btn)

        copy_table_layout = QtWidgets.QVBoxLayout()
        copy_table_layout.addWidget(self.copy_table)
        
        pages_layout = QtWidgets.QHBoxLayout()
        pages_layout.addWidget(self.page_left_btn)
        pages_layout.addWidget(self.page_le)
        pages_layout.addWidget(self.page_right_btn)
        pages_layout.addStretch()

        main_copy_layout = QtWidgets.QVBoxLayout()
        main_copy_layout.addLayout(filter_layout)
        main_copy_layout.addLayout(copy_table_layout)
        main_copy_layout.addLayout(pages_layout)

        copy_table_grp = QtWidgets.QGroupBox("Netcopies")
        copy_table_grp.setLayout(main_copy_layout)

        self.splitter.addWidget(copy_table_grp)

        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addWidget(self.refresh_btn)
        button_layout.addStretch()
        button_layout.addWidget(self.close_btn)
        
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.addLayout(send_copy_layout)
        main_layout.addWidget(self.splitter)
        main_layout.addLayout(button_layout)

    def create_connections(self):
        """Create all connections for the UI"""
        self.make_copies_table()
        self.send_btn.clicked.connect(self.export_copy)
        self.filter_btn.clicked.connect(self.make_copies_table)
        self.page_left_btn.clicked.connect(self.previous_page)
        self.page_right_btn.clicked.connect(self.next_page)
        self.page_le.editingFinished.connect(self.get_current_page)
        self.refresh_btn.clicked.connect(self.make_copies_table)
        self.close_btn.clicked.connect(self.close)

    def previous_page(self):
        if self.page_num > 0:
            self.page_num -= 1
            self.page_le.setText(str(self.page_num + 1))
            self.get_current_page()

    def next_page(self):
        if len(self.filtered_copies) > (self.page_num + 1) * 10:
            self.page_num += 1
            self.page_le.setText(str(self.page_num + 1))
            self.get_current_page()

    def export_copy(self):
        copy_name = self.send_le.text()
        if not copy_name:
            QtWidgets.QMessageBox.warning(self, "Input Error", "Please enter a name for the copy.")
            return

        self.netcopy.export_selection(copy_name, self.storage_path)
        self.make_copies_table()

    def make_copies_table(self):
        # Reset table and retrieve all copies
        self.copy_table.setRowCount(0)

        filter_text = self.filter_le.text()

        self.copies = self.netcopy.get_all_copies(self.storage_path)
        self.filtered_copies = []

        # Setup copies table
        for copy, time in self.copies.items():
            copy_name = copy.stem
            formatted_time = time

            if filter_text.lower() in copy_name.lower():
                self.filtered_copies.append(copy)

                index = self.copy_table.rowCount()
                self.copy_table.setRowCount(index + 1)

                # Copy Name Column
                name_item = QtWidgets.QTableWidgetItem(copy_name)
                name_item.setFlags(name_item.flags() & ~QtCore.Qt.ItemIsEditable)
                self.copy_table.setItem(index, 0, name_item)

                # Time Column
                time_item = QtWidgets.QTableWidgetItem(formatted_time)
                time_item.setFlags(time_item.flags() & ~QtCore.Qt.ItemIsEditable)
                self.copy_table.setItem(index, 1, time_item)

                # Paste Button
                apply_btn = QtWidgets.QPushButton("Paste", default=False, autoDefault=False)
                self.copy_table.setCellWidget(index, 2, apply_btn)
                apply_btn.clicked.connect(partial(self.netcopy.import_copy, copy))
        
        self.get_current_page()

        header = self.copy_table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)

    def get_current_page(self):
        page_num = int(self.page_le.text()) - 1

        if page_num < 0:
            self.page_num = 0
        elif len(self.filtered_copies) < 11:
            self.page_num = 0
        elif len(self.filtered_copies) == page_num * 10:
            self.page_num = int((len(self.filtered_copies) / 10) - 1)
        elif len(self.filtered_copies) < page_num * 10:
            if len(self.filtered_copies) % 10 == 0:
                self.page_num = int((len(self.filtered_copies) / 10) - 1)
            else:
                self.page_num = math.floor(len(self.filtered_copies) / 10)
        else:
            self.page_num = page_num

        self.page_le.setText(str(self.page_num + 1))

        self.show_table_items()

    def show_table_items(self):
        for i in range(self.copy_table.rowCount()):
            if i >= self.page_num * 10 and i < (self.page_num * 10) + 10:
                self.copy_table.setRowHidden(i, False)
            else:
                self.copy_table.setRowHidden(i, True)
