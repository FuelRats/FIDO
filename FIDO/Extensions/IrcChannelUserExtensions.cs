using System.Linq;
using IrcDotNet;

namespace FIDO.Extensions
{
  public static class IrcChannelUserExtensions
  {
    private static readonly char[] moderatorUserModes = { '~', '&', '@', '%' };
    private static readonly string[] moderatorHostnames = { "admin.fuelrats.com", "netadmin.fuelrats.com" };

    public static bool IsModerator(this IrcChannelUser ircChannelUser)
    {
      return HasAdminHostname(ircChannelUser) || HasAdminUserMode(ircChannelUser);
    }

    private static bool HasAdminUserMode(IrcChannelUser ircChannelUser)
    {
      return ircChannelUser.Modes.Intersect(moderatorUserModes).Any();
    }

    private static bool HasAdminHostname(IrcChannelUser ircChannelUser)
    {
      return moderatorHostnames.Any(h => h == ircChannelUser.User.HostName);
    }
  }
}