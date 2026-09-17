using Guider.Windows.Auth;

static void Check(bool value, string name)
{
    if (!value) throw new Exception(name);
}
static void Refused(Action action, string name)
{
    try { action(); }
    catch (ArgumentException) { return; }
    catch (InvalidOperationException) { return; }
    throw new Exception(name);
}

Check(PkceAttempt.ChallengeFor("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk")
    == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM", "RFC 7636 vector");
var now = DateTimeOffset.UtcNow;
var redirect = new Uri("http://127.0.0.1:49152/callback/");
var attempt = new PkceAttempt(redirect, now);
var callback = new Uri($"{redirect}?code=synthetic&state={attempt.State}");
var accepted = attempt.Consume(callback, now);
Check(accepted.Code == "synthetic" && accepted.Verifier.Length == 43, "Valid callback");
Refused(() => attempt.Consume(callback, now), "Replay accepted");
var second = new PkceAttempt(redirect, now);
Check(second.State != attempt.State && second.Challenge != attempt.Challenge, "Independent entropy");
Refused(() => second.Consume(new Uri($"{redirect}?code=x&state=wrong"), now), "Wrong state");
Refused(() => second.Consume(new Uri($"http://localhost:49152/callback/?code=x&state={second.State}"), now), "Wrong host");
Refused(() => second.Consume(new Uri($"{redirect}?code=x&state={second.State}&state={second.State}"), now), "Duplicate state");
Refused(() => second.Consume(new Uri($"{redirect}?code=x&state={second.State}"), now.AddMinutes(6)), "Expired attempt");
Refused(() => new PkceAttempt(new Uri("https://example.com/callback/"), now), "Remote callback");
Console.WriteLine("9 synthetic native PKCE checks passed. No identity service was contacted.");
