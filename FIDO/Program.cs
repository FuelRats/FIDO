using System;
using System.Threading.Tasks;
using Microsoft.Extensions.Configuration;

namespace FIDO
{
  public class Program
  {
    private static bool run = true;

    private static async Task Main()
    {
      var configurationBuilder = new ConfigurationBuilder();
      configurationBuilder.AddJsonFile("settings.json");

      var configuration = configurationBuilder.Build();

      Console.CancelKeyPress += ConsoleOnCancelKeyPress;
      await RunFido(configuration);
      Console.ReadKey();
    }

    private static async Task RunFido(IConfiguration configuration)
    {
      var fido = new Fido(configuration);
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