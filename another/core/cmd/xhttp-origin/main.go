package main

import (
	"log"
	"net/http"
	"os"

	"github.com/another-vpn/another/core/internal/adapters/transport/xhttp"
)

func main() {
	addr := os.Getenv("ANOTHER_XHTTP_ADDR")
	if addr == "" {
		addr = "127.0.0.1:8081"
	}
	log.Printf("another xhttp-origin listening on %s%s", addr, xhttp.DefaultPath)
	if err := http.ListenAndServe(addr, xhttp.NewServer()); err != nil {
		log.Fatal(err)
	}
}
