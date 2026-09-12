# Windows shell scaffold

Requires the [.NET 10 SDK](https://learn.microsoft.com/en-us/dotnet/core/whats-new/dotnet-10/overview) on Windows. Run `dotnet build Guider.Windows.csproj` or `dotnet run --project Guider.Windows.csproj` from this directory.

This independently scoped WPF shell displays an honest inactive status. It contains no capture, microphone, native login, input injection, overlay or execution features. Those belong to later implementation phases.

The .NET SDK is not installed in the initial coding environment, so this scaffold has not been built or manually exercised. Phase 0 still requires the synthetic native PKCE feasibility spike. No signed distributable is provided.
