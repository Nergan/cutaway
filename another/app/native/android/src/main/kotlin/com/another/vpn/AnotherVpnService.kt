package com.another.vpn

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Intent
import android.net.VpnService
import android.os.Build
import android.os.ParcelFileDescriptor
import mobilelib.Mobilelib
import java.util.concurrent.Executors

/**
 * VpnService — только интерфейс и kill switch (blocking, без allowBypass).
 * Трафик читает Go через fd (mobilelib.SetTunFd).
 */
class AnotherVpnService : VpnService() {

    private val worker = Executors.newSingleThreadExecutor()
    private var tun: ParcelFileDescriptor? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                stopTunnel()
                return START_NOT_STICKY
            }
            ACTION_START -> {
                val clientId = intent.getStringExtra(EXTRA_CLIENT_ID) ?: return START_NOT_STICKY
                val keyStore = intent.getStringExtra(EXTRA_KEYSTORE) ?: return START_NOT_STICKY
                val nodes = intent.getStringExtra(EXTRA_NODES) ?: "[]"
                val destHost = intent.getStringExtra(EXTRA_DEST_HOST) ?: ""
                val destPort = intent.getIntExtra(EXTRA_DEST_PORT, 0)
                startForeground(NOTIF_ID, notification())
                worker.execute { startTunnel(clientId, keyStore, nodes, destHost, destPort) }
            }
        }
        return START_STICKY
    }

    private fun startTunnel(
        clientId: String,
        keyStore: String,
        nodes: String,
        destHost: String,
        destPort: Int,
    ) {
        val builder = Builder()
            .setSession("Another")
            .setMtu(1500)
            .addAddress("10.7.0.2", 32)
            .addRoute("0.0.0.0", 0)
            .addDnsServer("1.1.1.1")
            .setBlocking(true)
        builder.setUnderlyingNetworks(null)
        // allowBypass по умолчанию false — kill switch: трафик только в TUN.
        val established = builder.establish() ?: return
        tun = established
        val fd = established.fd
        val fdJson = Mobilelib.SetTunFd(fd.toLong())
        if (!ok(fdJson)) return
        val armed = Mobilelib.NotifyKillSwitchArmed()
        if (!ok(armed)) return
        val init = Mobilelib.Init(clientId, keyStore, nodes)
        if (!ok(init)) return
        Mobilelib.Connect(destHost, destPort.toLong())
    }

    private fun stopTunnel() {
        worker.execute {
            Mobilelib.Disconnect()
            tun?.close()
            tun = null
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf()
        }
    }

    override fun onDestroy() {
        tun?.close()
        tun = null
        super.onDestroy()
    }

    private fun notification(): Notification {
        val mgr = getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= 26) {
            mgr.createNotificationChannel(
                NotificationChannel(CHANNEL_ID, "Another VPN", NotificationManager.IMPORTANCE_LOW)
            )
        }
        val b = if (Build.VERSION.SDK_INT >= 26) {
            Notification.Builder(this, CHANNEL_ID)
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(this)
        }
        return b.setContentTitle("Another")
            .setContentText("VPN connected")
            .setSmallIcon(android.R.drawable.stat_sys_warning)
            .build()
    }

    private fun ok(json: String): Boolean = json.contains("\"ok\":true")

    companion object {
        const val ACTION_START = "com.another.vpn.START"
        const val ACTION_STOP = "com.another.vpn.STOP"
        const val EXTRA_CLIENT_ID = "clientId"
        const val EXTRA_KEYSTORE = "keyStoreDir"
        const val EXTRA_NODES = "nodesJson"
        const val EXTRA_DEST_HOST = "destHost"
        const val EXTRA_DEST_PORT = "destPort"
        private const val CHANNEL_ID = "another.vpn"
        private const val NOTIF_ID = 7
    }
}
