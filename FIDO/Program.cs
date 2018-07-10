using System;
using System.Threading.Tasks;

namespace FIDO
{
  public class Program
  {
    private static bool run = true;

    private static async Task Main()
    {
      Console.CancelKeyPress += ConsoleOnCancelKeyPress;
      await RunFido();
      Console.ReadKey();
    }

    private static async Task RunFido()
    {
      var fido = new Fido();
      await fido.Run();

      while (run)
      {
        var line = Console.ReadLine();
        fido.SendRawMessage(line);
      }

      await fido.Disconnect();
    }

    private static void ConsoleOnCancelKeyPress(object sender, ConsoleCancelEventArgs e)
    {
      e.Cancel = true;
      run = false;
    }
  }
}