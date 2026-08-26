package xhttp

import (
	"bufio"
	"fmt"
	"io"
	"net"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/another-vpn/another/core/internal/adapters/transport/vlessproto"
)

// Server — origin-сторона split-HTTP. GET (downlink) + POST (uplink) с
// одним sid склеиваются в дуплекс, затем VLESS-заголовок и TCP к dest.
type Server struct {
	mu       sync.Mutex
	sessions map[string]*session
}

type session struct {
	mu      sync.Mutex
	up      io.ReadCloser
	down    http.ResponseWriter
	fl      http.Flusher
	started bool
	done    chan struct{}
}

func NewServer() *Server {
	return &Server{sessions: map[string]*session{}}
}

func sidFromPath(path string) string {
	path = strings.Trim(path, "/")
	if i := strings.LastIndex(path, "/"); i >= 0 {
		return path[i+1:]
	}
	return path
}

func (s *Server) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	sid := sidFromPath(r.URL.Path)
	if sid == "" || sid == strings.Trim(DefaultPath, "/") {
		http.Error(w, "missing session", http.StatusBadRequest)
		return
	}

	s.mu.Lock()
	sess, ok := s.sessions[sid]
	if !ok {
		sess = &session{done: make(chan struct{})}
		s.sessions[sid] = sess
	}
	s.mu.Unlock()

	switch r.Method {
	case http.MethodGet:
		fl, ok := w.(http.Flusher)
		if !ok {
			http.Error(w, "flush required", 500)
			return
		}
		w.Header().Set("Content-Type", "application/octet-stream")
		w.Header().Set("Cache-Control", "no-store")
		w.WriteHeader(http.StatusOK)
		fl.Flush()
		sess.mu.Lock()
		sess.down = w
		sess.fl = fl
		sess.mu.Unlock()
		s.maybeStart(sid, sess)
		select {
		case <-sess.done:
		case <-r.Context().Done():
		}
	case http.MethodPost:
		sess.mu.Lock()
		sess.up = r.Body
		sess.mu.Unlock()
		s.maybeStart(sid, sess)
		select {
		case <-sess.done:
		case <-r.Context().Done():
		}
	default:
		http.Error(w, "method", http.StatusMethodNotAllowed)
	}
}

func (s *Server) maybeStart(sid string, sess *session) {
	sess.mu.Lock()
	defer sess.mu.Unlock()
	if sess.started || sess.up == nil || sess.down == nil {
		return
	}
	sess.started = true
	go s.proxy(sid, sess)
}

func (s *Server) proxy(sid string, sess *session) {
	defer func() {
		close(sess.done)
		s.mu.Lock()
		delete(s.sessions, sid)
		s.mu.Unlock()
	}()

	br := bufio.NewReader(sess.up)
	hdr, err := vlessproto.DecodeRequestHeader(br)
	if err != nil {
		return
	}
	conn, err := net.DialTimeout("tcp", net.JoinHostPort(hdr.DestHost, fmt.Sprintf("%d", hdr.DestPort)), 10*time.Second)
	if err != nil {
		return
	}
	defer conn.Close()
	if err := vlessproto.EncodeResponseHeader(sess.down); err != nil {
		return
	}
	sess.fl.Flush()

	errCh := make(chan struct{}, 2)
	go func() {
		_, _ = io.Copy(conn, br)
		errCh <- struct{}{}
	}()
	go func() {
		buf := make([]byte, 32*1024)
		for {
			n, err := conn.Read(buf)
			if n > 0 {
				_, _ = sess.down.Write(buf[:n])
				sess.fl.Flush()
			}
			if err != nil {
				errCh <- struct{}{}
				return
			}
		}
	}()
	<-errCh
}
