package app

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net"
	"net/url"

	"github.com/another-vpn/another/core/internal/domain"
	"github.com/another-vpn/another/core/internal/ports"
)

var ErrAllNodesFailed = errors.New("app: all candidate nodes failed")

type ConnectUseCase struct {
	Session     *domain.TunnelSession
	KeyStore    ports.KeyStorePort
	Auth        ports.AuthPort
	Transport   ports.OutboundTransportPort
	Tunnel      ports.TunnelPort
	KillSwitch  ports.KillSwitchPort
	RateLimiter ports.RateLimiterPort
	Prober      ports.ProbePort
	Logger      *slog.Logger
	ClientID    string
}

func NewConnectUseCase(
	session *domain.TunnelSession,
	keyStore ports.KeyStorePort,
	auth ports.AuthPort,
	transport ports.OutboundTransportPort,
	tunnelPort ports.TunnelPort,
	killSwitch ports.KillSwitchPort,
	rateLimiter ports.RateLimiterPort,
	clientID string,
	logger *slog.Logger,
) *ConnectUseCase {
	if logger == nil {
		logger = slog.Default()
	}
	return &ConnectUseCase{
		Session: session, KeyStore: keyStore, Auth: auth, Transport: transport,
		Tunnel: tunnelPort, KillSwitch: killSwitch, RateLimiter: rateLimiter,
		ClientID: clientID, Logger: logger,
	}
}

// Execute: destHost=="" && destPort==0 — VPN (TUN + NAT на каждый поток).
// Иначе — один VLESS-поток (тесты / ручной прокси).
func (uc *ConnectUseCase) Execute(ctx context.Context, policy *domain.FailoverPolicy, destHost string, destPort uint16) error {
	uc.Session.SetConnecting()

	nodes := policy.Ordered()
	if uc.Prober != nil && len(nodes) > 0 {
		results := uc.Prober.Probe(ctx, nodes)
		nodes = domain.OrderByProbe(nodes, results)
		for _, r := range results {
			uc.Logger.Info("probe", "node", r.Name, "ok", r.OK, "rtt_ns", r.RTT, "err", r.Err)
		}
	}

	if setter, ok := uc.KillSwitch.(ports.DestinationPermitter); ok {
		setter.SetPermitDestinations(permitHosts(nodes))
	}

	if err := uc.KillSwitch.Arm(ctx); err != nil {
		uc.Session.SetFailed(err)
		return fmt.Errorf("app: killswitch arm: %w", err)
	}

	identity, err := uc.KeyStore.LoadOrCreateDeviceIdentity()
	if err != nil {
		uc.Session.SetFailed(err)
		return fmt.Errorf("app: load device identity: %w", err)
	}

	vpn := destHost == "" && destPort == 0
	var lastErr error
	for _, node := range nodes {
		select {
		case <-ctx.Done():
			uc.Session.SetFailed(ctx.Err())
			return ctx.Err()
		default:
		}
		uc.Logger.Info("trying node", "node", node.Name, "tier", node.Tier.String(), "transport", node.Transport.String(), "vpn", vpn)

		creds, err := uc.Auth.ChallengeResponse(ctx, node, uc.ClientID, identity)
		if err != nil {
			uc.Logger.Warn("node auth failed", "node", node.Name, "error", err)
			lastErr = err
			continue
		}

		if vpn {
			stack, ok := uc.Tunnel.(ports.StackBinder)
			if !ok {
				lastErr = fmt.Errorf("app: tun adapter does not support VPN stack")
				continue
			}
			nodeCopy := node
			credsCopy := *creds
			dial := func(dctx context.Context, network, host string, port uint16) (ports.Tunnel, error) {
				return uc.Transport.Dial(dctx, nodeCopy, &credsCopy, host, port)
			}
			if err := stack.BindDialer(ctx, dial); err != nil {
				uc.Logger.Warn("tun stack bind failed", "node", node.Name, "error", err)
				lastErr = err
				continue
			}
			uc.Session.SetConnected(&nodeCopy)
			uc.Logger.Info("connected vpn", "node", node.Name)
			return nil
		}

		tunnel, err := uc.Transport.Dial(ctx, node, creds, destHost, destPort)
		if err != nil {
			uc.Logger.Warn("node dial failed", "node", node.Name, "error", err)
			lastErr = err
			continue
		}
		if err := uc.Tunnel.Bind(ctx, tunnel); err != nil {
			uc.Logger.Warn("tun bind failed", "node", node.Name, "error", err)
			_ = tunnel.Close()
			lastErr = err
			continue
		}
		nodeCopy := node
		uc.Session.SetConnected(&nodeCopy)
		uc.Logger.Info("connected", "node", node.Name)
		return nil
	}

	uc.Session.SetFailed(lastErr)
	if lastErr != nil {
		return fmt.Errorf("%w: last error: %v", ErrAllNodesFailed, lastErr)
	}
	return ErrAllNodesFailed
}

func permitHosts(nodes []domain.NodeDescriptor) []string {
	seen := map[string]struct{}{}
	var out []string
	addHost := func(host string) {
		if host == "" {
			return
		}
		ips, err := net.LookupIP(host)
		if err != nil {
			return
		}
		for _, ip := range ips {
			s := ip.String()
			if _, ok := seen[s]; ok {
				continue
			}
			seen[s] = struct{}{}
			out = append(out, s)
		}
	}
	for _, n := range nodes {
		addHost(n.Host)
		if n.ControlPlane != "" {
			if u, err := url.Parse(n.ControlPlane); err == nil {
				addHost(u.Hostname())
			}
		}
	}
	return out
}
