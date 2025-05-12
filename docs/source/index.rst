
.. image:: _static/icon.png
   :width: 100px
   :height: 100px
   :alt: ExpenseTracker icon
   :align: left


ExpenseTracker
==============


.. image:: https://img.shields.io/badge/License-GPLv3-black.svg
   :target: https://opensource.org/license/gpl-3-0
   :alt: License: GPLv3

.. image:: https://img.shields.io/badge/Python-Python3.11+-black.svg
   :alt: Python 3.11+
   :target: https://www.python.org/downloads/release/python-3110

   
.. image:: https://img.shields.io/badge/Qt-PySide6-black.svg
   :alt: Qt6/PySide6
   :target: https://doc.qt.io/qtforpython-6/index.html

.. image:: https://github.com/wgergely/ExpenseTracker/actions/workflows/test.yml/badge.svg
   :alt: Test


------


**ExpenseTracker is a personal finance desktop app for visualizing expenses stored in Google Sheets.**


.. image:: _static/ui_darklight.png
   :width: 600px
   :alt: ExpenseTracker UI
   :align: center


-------

If you use Google Sheets to track personal expenses, you might have thougth at one point, huh,
wouldn't it be nice to have a dedicated app that can visualize my spreadsheet? I know, you didn't think that.
But I did, and I built one, and you're looking at it!

Before you get your hopes up, ExpenseTracker is limited and boots only a limited feature set.


What does it do?
++++++++++++++++

| ✅ Fetches data from Google Sheets and display expenses by period and category
| ✅ Displays expenses by period
| ✅ You can save preset, to allow switching between multiple sources and or insights
| ✅ Browse and edit category transactions
| ✅ Basic data visualization
| ✅ Arrange, exclude and customize categories


What it doesn't do:
+++++++++++++++++++

| ❌ Source data editing isn't fully supported (only category editing)



Quick Start
===========

Download and install the latest release (Windows only, sorry!) from the releases page:

| 🔽 `Latest Release on Github <https://https://github.com/wgergely/ExpenseTracker/releases/>`_


| 🔘 Google Cloud Project 

You'll have to set up a Google Cloud Project and an OAuth 2.0 client ID to access the Google Sheets API.
The process is a little cumbersome, but without this data cannot be fetched from SPreadhseet sources.




Contact
=======

| Gergely Wootsch
| Email: `hello+ExpenseTracker@gergely-wootsch.com <hello+ExpenseTracker@gergely-wootsch.com>`_



.. toctree::
   :maxdepth: 2
   :caption: Contents:

   user_guide/index
   api/index