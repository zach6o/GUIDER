# Windows shell scaffold

Requires the [.NET 10 SDK](https://learn.microsoft.com/en-us/dotnet/core/whats-new/dotnet-10/overview) on Windows. Run `dotnet build Guider.Windows.csproj` or `dotnet run --project Guider.Windows.csproj` from this directory.

This independently scoped WPF shell displays an honest inactive status. It contains no capture, microphone, native login, input injection, overlay or execution features. Those belong to later implementation phases.

The shell was built on 2026-09-17 with .NET SDK 10.0.401: zero warnings and errors. `Auth/PkceAttempt.cs` implements fresh verifier/state entropy, S256 challenges, exact loopback callback matching, five-minute expiry and single-use consumption. Nine synthetic checks pass, including the RFC 7636 test vector, callback mismatch, replay and duplicate-field rejection.

Run the checks with `dotnet run --project ../windows-tests/Guider.NativeChecks.csproj --configuration Release`. Windows CI builds the shell and runs the same checks. This is a bounded authentication spike: no browser callback listener, token exchange, refresh storage, Supabase session, capture, overlay or signed distributable is implemented or certified.
