# TODO

## Security Hardening

- Rotate the Telegram bot token and database credentials, then update the live service environment.
- Add an audit trail for wallet/user mutations, especially add/remove wallet actions and rejected unauthorized bot interactions.
- Add regression coverage for private-bot authorization so only `WHITELISTED_USER_ID` can use Telegram commands and callbacks.
- Review public-facing auxiliary services, especially dashboard and Alchemy webhook exposure, before deploying beyond localhost.
