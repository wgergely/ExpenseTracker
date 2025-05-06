
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

   
.. image:: https://img.shields.io/badge/Qtw-PySide6-black.svg
   :alt: Qt6/PySide6
   :target: https://doc.qt.io/qtforpython-6/index.html




------


**ExpenseTracker is a personal financce desktop app for visualizing expenses stored in a Google Sheets.**


-------

If you are like me, and use Google Sheets to track personal expenses, you might have thougth at one point, huh,
wouldn't it be nice to have a dedicated app that can visualize my spreadsheet? I know, sheets does charts but it is a bit clunky.
Anyhow, I did think that and I did built one, and you're looking at it!

Before you get your hopes up, ExpenseTracker is a pretty basic and boots only a limited feature set.

What does it do?
++++++++++++++++

| ✅ Fetches data from Google Sheets and display expenses by period and category
| ✅ Fitler data by period
| ✅ Manages presets, to allow switching between multiple sources and or insights modes
| ✅ browse transactions by category
| ✅ edit transaction categories
| ✅ display data in simple charts
| ✅ arrange, exclude and customize categories


What it doesn't do:
+++++++++++++++++++

| ❌ doesn't (yet) support editing source data


Quick Start
===========


| 🔽 `Latest Release on Github <https://https://github.com/wgergely/ExpenseTracker/releases/>`_



Download and install the latest release.

The app needs a Google Cloud project and an OAuth 2.0 client ID to access the Google Sheets API.
It is a bit cumbersome to set up but is necessary to fetch data from your Google Sheet sources.

Follow these instructions:


This documentation covers installation, configuration. For immediate access, see the :doc:installation instructions
<user_guide/installation>, the :doc:quick start guide <user_guide/quick_start>, or visit the project's download page
<https://github .com/wgergely/ExpenseTracker/releases>_.

Developers looking to extend or integrate ExpenseTracker can find comprehensive API documentation in the :doc:API
Reference <api/index>.

Credits
-------

Gergely Wootsch
Email: [



.. toctree::
   :maxdepth: 2
   :caption: Contents:

   user_guide/index
   api/index