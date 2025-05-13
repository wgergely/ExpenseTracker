# Google Cloud Platform Setup

The app requires a valid [Google API client ID](https://developers.google.
com/identity/oauth2/web/guides/get-google-api-clientid) to connect with your account and Google Sheets document.
Follow these steps to set up your Google Cloud Platform (GCP) project and get the necessary credentials:

#### Google Cloud Project

- Pick or create a new [Google Cloud Platform project](https://developers.google.com/workspace/guides/create-project).
- Enable the required [Google Sheets API](https://cloud.google.com/endpoints/docs/openapi/enable-api) in the [API Library](https://console.cloud.google.com/apis/library).

#### Client ID

Set up a new OAuth client ID in the [Credentials](https://console.cloud.google.com/apis/credentials) section of your project:

Click on "Create credentials" and select "OAuth client ID".
  - Configure the consent screen with the necessary information.
  - Choose "Desktop app" as the app type.
- Download the generated JSON.

The generated JSON should look something like this:

```json 
{
  "installed": {
    "client_id": "<CLIEND-ID>.apps.googleusercontent.com",
    "project_id": "<PROJECT-ID>",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_secret": "secret",
    "redirect_uris": [
      "http://localhost"
    ]
  }
}
