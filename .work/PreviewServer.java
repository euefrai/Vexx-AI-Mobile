import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Map;

public class PreviewServer {
  static final Path ROOT = Paths.get("public").toAbsolutePath().normalize();
  static final Map<String,String> TYPES = Map.of(
      ".html", "text/html; charset=utf-8", ".css", "text/css; charset=utf-8",
      ".js", "text/javascript; charset=utf-8", ".svg", "image/svg+xml",
      ".png", "image/png", ".webmanifest", "application/manifest+json"
  );
  public static void main(String[] args) throws Exception {
    HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 8899), 0);
    server.createContext("/", PreviewServer::handle);
    server.start();
    System.out.println("PREVIEW_SERVER http://127.0.0.1:8899/");
    Thread.currentThread().join();
  }
  static void handle(HttpExchange ex) throws IOException {
    String raw = ex.getRequestURI().getPath();
    if (raw == null || raw.equals("/") || raw.isBlank()) raw = "/index.html";
    Path file = ROOT.resolve(raw.substring(1)).normalize();
    if (!file.startsWith(ROOT) || !Files.isRegularFile(file)) {
      byte[] body = "Not found".getBytes();
      ex.sendResponseHeaders(404, body.length);
      try (OutputStream out = ex.getResponseBody()) { out.write(body); }
      return;
    }
    byte[] body = Files.readAllBytes(file);
    String name = file.getFileName().toString();
    String ext = name.contains(".") ? name.substring(name.lastIndexOf('.')) : "";
    String type = TYPES.getOrDefault(ext, "application/octet-stream");
    ex.getResponseHeaders().set("Content-Type", type);
    ex.sendResponseHeaders(200, body.length);
    try (OutputStream out = ex.getResponseBody()) { out.write(body); }
  }
}
