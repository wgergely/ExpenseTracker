# ExpenseTracker

ExpenseTracker is a desktop application that reads data from a Google Sheets ledger to analyze expenses. This repository is open-source but intended for personal use. Below is how the Google OAuth authentication flow works.

## Google OAuth Authentication

### Overview  
   - ExpenseTracker uses the Google Sheets API to read your spreadsheet data.  
   - Authentication is handled via the `ExpensesTracker/lib/google/auth.py` module, which uses the Google OAuth “InstalledAppFlow.”  
   - This allows you to sign in via your default web browser and grant read/write permissions to your spreadsheet.

### Included OAuth Client Credentials  
   - This project includes a default OAuth client file (`default_client_secrets.json`) in `ExpensesTracker/lib`.  
   - **Note**: Because ExpenseTracker is a desktop/installed application, the `client_secret` is effectively public. For personal use, this is usually fine. If you prefer more control, you can [create your own OAuth client](https://console.cloud.google.com/apis/credentials) in Google Cloud, and update the file yourself.

### How It Works  
   - When you run ExpenseTracker, the app checks for existing credentials in a local cache (in your OS temp directory).
   - If no valid credentials are found, a new OAuth flow starts, launching your default web browser.
   - You review and accept the permissions request.  
   - The app receives an authorization code and gets an access/refresh token, which it stores locally for future runs.  
   - Later runs use the cached credentials and only prompt for re-auth if the token is revoked, expired, or missing.

### Creating Your Own OAuth Client (Optional)  
   - If you do **not** want to use the default credentials, or if you plan to distribute a fork, it’s recommended you create your own client ID under **APIs & Services → Credentials** in Google Cloud Console.  
   - Set the **Application Type** to **Desktop App**.  
   - Download the JSON file and replace the existing `default_client_secrets.json`.  
   - Alternatively, set the path via an environment variable or application setting.

### Security Considerations  
   - The included “client secret” is not truly secret in a desktop app. Google’s policies for “Installed” apps acknowledge this.  
   - For personal use, this is generally acceptable because your final data is still protected by the OAuth consent flow.  
   - If distributing widely, consider rotating credentials, restricting them, or letting each user supply their own.