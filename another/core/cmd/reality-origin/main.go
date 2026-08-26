// Command reality-origin — Reality-вход на VPS (фаза 4).
//
//	reality-origin -keygen
//	reality-origin -probe www.microsoft.com:443
//	ANOTHER_REALITY_PRIVATE_KEY=... ANOTHER_REALITY_DEST=www.example.com:443 \
//	  ANOTHER_REALITY_SHORT_IDS=aabbccdd ANOTHER_REALITY_SERVER_NAMES=www.example.com \
//	  reality-origin
package main

import (
	"encoding/hex"
	"flag"
	"fmt"
	"log"
	"net"
	"os"
	"strings"
	"time"

	"github.com/another-vpn/another/core/internal/adapters/transport"
)

func main() {
	keygen := flag.Bool("keygen", false, "напечатать пару X25519 (priv/pub hex)")
	probe := flag.String("probe", "", "TLS-проверка SNI-донора host:port")
	probeSNI := flag.String("probe-sni", "", "SNI для -probe (по умолчанию host)")
	listen := flag.String("listen", envOr("ANOTHER_REALITY_LISTEN", "127.0.0.1:8443"), "адрес Reality")
	dest := flag.String("dest", os.Getenv("ANOTHER_REALITY_DEST"), "SNI-донор host:port для probe-fallback")
	privHex := flag.String("private-key", os.Getenv("ANOTHER_REALITY_PRIVATE_KEY"), "X25519 private hex")
	shortIDs := flag.String("short-ids", os.Getenv("ANOTHER_REALITY_SHORT_IDS"), "shortId hex, через запятую")
	names := flag.String("server-names", os.Getenv("ANOTHER_REALITY_SERVER_NAMES"), "разрешённые SNI, через запятую")
	flag.Parse()

	if *keygen {
		priv, pub, err := transport.GenerateRealityKeypair()
		if err != nil {
			log.Fatal(err)
		}
		fmt.Printf("ANOTHER_REALITY_PRIVATE_KEY=%s\n", priv)
		fmt.Printf("# reality_public_key в nodes JSON:\n%s\n", pub)
		return
	}
	if *probe != "" {
		info, err := transport.ProbeDonor(*probe, *probeSNI, 8*time.Second)
		if err != nil {
			log.Fatal(err)
		}
		fmt.Println(info.String())
		return
	}

	if *privHex == "" {
		log.Fatal("нужен -private-key / ANOTHER_REALITY_PRIVATE_KEY (сначала -keygen)")
	}
	priv, err := transport.ParseRealityPrivateKey(*privHex)
	if err != nil {
		log.Fatal(err)
	}
	var ids [][]byte
	for _, p := range splitCSV(*shortIDs) {
		b, err := hex.DecodeString(p)
		if err != nil || len(b) > 8 {
			log.Fatalf("bad short-id %q", p)
		}
		ids = append(ids, b)
	}
	srv := transport.NewRealityServer(priv, *dest, ids, splitCSV(*names), nil)
	ln, err := net.Listen("tcp", *listen)
	if err != nil {
		log.Fatal(err)
	}
	log.Printf("another reality-origin listening on %s dest=%s", *listen, *dest)
	if err := srv.Serve(ln); err != nil {
		log.Fatal(err)
	}
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func splitCSV(s string) []string {
	var out []string
	for _, p := range strings.Split(s, ",") {
		p = strings.TrimSpace(p)
		if p != "" {
			out = append(out, p)
		}
	}
	return out
}
