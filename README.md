# ExpenseTracker

## Setup

### client_secret.json

This file is used to authenticate the user with Google API. It contains the client ID and client secret for your app. You can create this file by following these steps:

- Go to the [Google Cloud Console](https://console.cloud.google.com/).
- Create a new project or select an existing one.
- Enable the Google Sheets API for your project.
- Navigate to API & Services > Credentials.
- Select "Create credentials" and choose "OAuth client ID".
- Configure the consent screen and select "Desktop app" as the app type.
- Save the generated `client_secret.json` file to the `ExpenseTracker/config` directory.

The generated JSON should look something like this:

```json

{
  "installed": {
    "client_id": "your-client-id.apps.googleusercontent.com",
    "project_id": "project-id",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_secret": "secret",
    "redirect_uris": [
      "http://localhost"
    ]
  }
}

```

### ledger_id

Make sure to create a file named `ledger_id` in the `ExpenseTracker/config` directory. This file should contain the id number of the source data sheet
as a single line, for example:

```
2fGHGyHub6j-LuBstCz1XmNby5HJu4suJv1S7idGIRfk
```

