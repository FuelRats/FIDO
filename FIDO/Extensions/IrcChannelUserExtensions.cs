using System.Linq;
using IrcDotNet;

namespace FIDO.Extensions
{
  public static class IrcChannelUserExtensions
  {
    private static readonly char[] moderatorUserModes = { '~', '&', '@', '%', 'q', 'a', 'o', 'h' };
    private static readonly string[] moderatorHostnames = { "admin.fuelrats.com", "netadmin.fuelrats.com" };

    public static bool IsModerator(this IrcChannelUser ircChannelUser)
    {
      return HasAdminHostname(ircChannelUser.User) || HasAdminUserMode(ircChannelUser);
    }

    public static bool IsModerator(this IrcUser ircUser)
    {
      return HasAdminHostname(ircUser);
    }

    private static bool HasAdminUserMode(IrcChannelUser ircChannelUser)
    {
      return ircChannelUser.Modes.Intersect(moderatorUserModes).Any();
    }

    private static bool HasAdminHostname(IrcUser ircUser)
    {
      return moderatorHostnames.Any(h => h == ircUser.HostName);
    }
  }
}