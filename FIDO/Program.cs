using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Configuration;

namespace FIDO
{
  public class Program
  {
    private static readonly ManualResetEvent manualResetEvent = new ManualResetEvent(false);
    private static Fido fido;
    private static bool run = true;

    private static async Task Main()
    {
      AppDomain.CurrentDomain.UnhandledException += AppDomainOnUnhandledException;
      var configurationBuilder = new ConfigurationBuilder();
      configurationBuilder.AddJsonFile("settings.json");

      var configuration = configurationBuilder.Build();

      Console.CancelKeyPress += ConsoleOnCancelKeyPress;
      fido = new Fido(configuration);
      fido.Disconnected += FidoOnDisconnected;
      await RunFido();

      Console.ReadKey();
    }

    private static void AppDomainOnUnhandledException(object sender, UnhandledExceptionEventArgs e)
    {
      Console.WriteLine(e.ExceptionObject);
    }

    private static async Task RunFido()
    {
      await fido.Run();
      manualResetEvent.WaitOne();

      if (fido.IsConnected)
      {
        await fido.Disconnect();
      }
    }

    private static async void FidoOnDisconnected(object sender, EventArgs e)
    {
      if (run)
      {
        await fido.Run();
      }
    }

    private static void ConsoleOnCancelKeyPress(object sender, ConsoleCancelEventArgs e)
    {
      e.Cancel = true;
      run = false;
      manualResetEvent.Set();
    }
  }
}