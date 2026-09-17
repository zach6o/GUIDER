using System.Security.Cryptography;
using System.Text;

namespace Guider.Windows.Auth;

/// <summary>A single-use, bounded PKCE attempt for the synthetic native auth spike.</summary>
public sealed class PkceAttempt
{
    private readonly string verifier = Base64Url(RandomNumberGenerator.GetBytes(32));
    private readonly DateTimeOffset expiresAt;
    private int consumed;
    public string State { get; } = Base64Url(RandomNumberGenerator.GetBytes(32));
    public string Challenge => ChallengeFor(verifier);
    public Uri RedirectUri { get; }

    public PkceAttempt(Uri redirectUri, DateTimeOffset now)
    {
        if (redirectUri.Scheme != "http" || redirectUri.Host != "127.0.0.1"
            || redirectUri.Port <= 0 || redirectUri.AbsolutePath != "/callback/"
            || redirectUri.Query.Length != 0 || redirectUri.Fragment.Length != 0
            || redirectUri.UserInfo.Length != 0)
            throw new ArgumentException("Use an exact IPv4 loopback callback.");
        RedirectUri = redirectUri;
        expiresAt = now.AddMinutes(5);
    }

    public (string Code, string Verifier) Consume(Uri callback, DateTimeOffset now)
    {
        if (now >= expiresAt || Interlocked.CompareExchange(ref consumed, 0, 0) != 0)
            throw new InvalidOperationException("Start a new sign-in attempt.");
        if (callback.GetLeftPart(UriPartial.Path) != RedirectUri.GetLeftPart(UriPartial.Path)
            || callback.Fragment.Length != 0 || callback.UserInfo.Length != 0)
            throw new ArgumentException("Callback address mismatch.");
        var query = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var item in callback.Query.TrimStart('?').Split('&', StringSplitOptions.RemoveEmptyEntries))
        {
            var pair = item.Split('=', 2);
            var key = Uri.UnescapeDataString(pair[0].Replace('+', ' '));
            var value = pair.Length == 2 ? Uri.UnescapeDataString(pair[1].Replace('+', ' ')) : "";
            if (!query.TryAdd(key, value)) throw new ArgumentException("Duplicate callback field.");
        }
        if (query.ContainsKey("error") || !query.TryGetValue("state", out var state)
            || !CryptographicOperations.FixedTimeEquals(Encoding.UTF8.GetBytes(state), Encoding.UTF8.GetBytes(State))
            || !query.TryGetValue("code", out var code) || string.IsNullOrWhiteSpace(code)
            || code.Length > 2048)
            throw new ArgumentException("Sign-in callback rejected.");
        if (Interlocked.Exchange(ref consumed, 1) != 0)
            throw new InvalidOperationException("This sign-in attempt was already used.");
        return (code, verifier);
    }

    public static string ChallengeFor(string verifier) =>
        Base64Url(SHA256.HashData(Encoding.ASCII.GetBytes(verifier)));

    private static string Base64Url(byte[] bytes) =>
        Convert.ToBase64String(bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_');
}
