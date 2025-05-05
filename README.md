# ExpenseTracker

<img src="..docs/rsc/icon.png" alt="ExpenseTracker icon" width="100" height="100"/>


ExpenseTracker is a desktop application that visualizes financial transactions grouped by category. The data is sourced
directly from Google Sheets, allowing to analyze spending across different periods.

---

## Who is ExpenseTracker for?

ExpenseTracker is designed for folk who already track their spending using Google Sheets and need a practical way to
visualize and understand their expenses.

---

## Features

- Direct integration with Google Sheets for data retrieval
- Presets for switching between different views
- Currency display preferences
- Flexible mapping of spreadsheet data
- Editable transactions and categories
- Synchronizable expense categories
- Visualization options for average and total expenses
- Dark and light themes

![Main UI Screenshot](path/to/screenshot.png)

---

## Installation

### Requirements

- Python 3.11 or later
- PySide6
- Windows OS (other platforms possible but require manual setup)

### Installation Steps

You can find the app's build tools in the `app` directory. The current CMake based build is only supported on Windows.
To build you can do the following:

```bash
git clone https://github.com/yourusername/ExpenseTracker.git
cd ExpenseTracker/app
./powershell -executionpolicy bypass -file ./build.ps1 -Config Release -BuildDir C:/build/
```

### Running the Application

Run ExpenseTracker by importing and executing it in Python:

```python
import ExpenseTracker

ExpenseTracker.exec_()
```

## Getting Started

ExpenseTracker requires you to configure access to your Google Spreadsheet by following the instructions in [
`./ExpenseTracker/config/gcp.md`](./ExpenseTracker/config/gcp.md).

## How to Contribute

### Reporting Issues

If you encounter bugs or issues, please open an issue on GitHub or submit a pull request clearly explaining the problem.

### Areas Needing Assistance

- Improving the authentication process
- Expanding and refining documentation

## License

ExpenseTracker uses the GPL v3 license.

## Contact

For support or questions, email [
`hello+ExpenseTracker@gergely-wootsch.com`](mailto:hello+ExpenseTracker@gergely-wootsch.com).

A Frequently Asked Questions (FAQ) section will be added based on common queries and user feedback.
