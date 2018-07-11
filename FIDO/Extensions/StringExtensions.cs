using FIDO.Irc;

namespace FIDO.Extensions
{
  public static class StringExtensions
  {
    public static string WrapWithColour(this string message, string colour, string resetColour = null)
    {
      if (!string.IsNullOrWhiteSpace(colour))
      {
        message = $"{colour}{message}{resetColour ?? Colours.Reset}";
      }

      return message;
    }
  }
}