package com.another.vpn

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.net.VpnService
import io.flutter.embedding.engine.plugins.FlutterPlugin
import io.flutter.embedding.engine.plugins.activity.ActivityAware
import io.flutter.embedding.engine.plugins.activity.ActivityPluginBinding
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import io.flutter.plugin.common.PluginRegistry
import mobilelib.Mobilelib
import org.json.JSONObject

/**
 * Тонкий клей MethodChannel → gomobile `Mobilelib.*`.
 * Не бизнес-логика: VPN-стек в Go. Kotlin только VpnService + канал.
 *
 * Канал: `another.core/control` (см. PlatformChannelCoreAdapter).
 * AAR из `gomobile bind -target=android ./cmd/mobilelib` кладётся в android/app/libs.
 */
class AnotherCorePlugin : FlutterPlugin, MethodChannel.MethodCallHandler, ActivityAware,
    PluginRegistry.ActivityResultListener {

    private lateinit var channel: MethodChannel
    private var activity: Activity? = null
    private var appContext: Context? = null
    private var pendingConnect: Pair<MethodCall, MethodChannel.Result>? = null

    override fun onAttachedToEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        appContext = binding.applicationContext
        channel = MethodChannel(binding.binaryMessenger, "another.core/control")
        channel.setMethodCallHandler(this)
    }

    override fun onDetachedFromEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        channel.setMethodCallHandler(null)
    }

    override fun onAttachedToActivity(binding: ActivityPluginBinding) {
        activity = binding.activity
        binding.addActivityResultListener(this)
    }

    override fun onDetachedFromActivity() {
        activity = null
    }

    override fun onReattachedToActivityForConfigChanges(binding: ActivityPluginBinding) {
        onAttachedToActivity(binding)
    }

    override fun onDetachedFromActivityForConfigChanges() {
        onDetachedFromActivity()
    }

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        try {
            when (call.method) {
                "getOrCreatePublicKey" -> {
                    val dir = call.argument<String>("keyStoreDir")
                        ?: throw IllegalArgumentException("keyStoreDir")
                    result.success(parseJson(Mobilelib.GetPublicKey(dir)))
                }
                "connect" -> prepareVpnThenConnect(call, result)
                "switchNode" -> {
                    val json = Mobilelib.SwitchNode(
                        call.argument<String>("nodeJson") ?: "",
                        call.argument<String>("destHost") ?: "",
                        (call.argument<Int>("destPort") ?: 0).toLong(),
                    )
                    result.success(parseJson(json))
                }
                "disconnect" -> {
                    activity?.startService(
                        Intent(activity, AnotherVpnService::class.java).setAction(AnotherVpnService.ACTION_STOP)
                    )
                    result.success(parseJson(Mobilelib.Disconnect()))
                }
                "status" -> result.success(parseJson(Mobilelib.Status()))
                else -> result.notImplemented()
            }
        } catch (e: Exception) {
            result.error("core", e.message, null)
        }
    }

    private fun prepareVpnThenConnect(call: MethodCall, result: MethodChannel.Result) {
        val act = activity
        if (act == null) {
            result.error("core", "no activity", null)
            return
        }
        val prep = VpnService.prepare(act)
        if (prep != null) {
            pendingConnect = call to result
            act.startActivityForResult(prep, REQ_VPN)
            return
        }
        startTunnel(call, result)
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?): Boolean {
        if (requestCode != REQ_VPN) return false
        val pending = pendingConnect
        pendingConnect = null
        if (pending == null) return true
        val (call, result) = pending
        if (resultCode != Activity.RESULT_OK) {
            result.error("core", "vpn permission denied", null)
            return true
        }
        startTunnel(call, result)
        return true
    }

    private fun startTunnel(call: MethodCall, result: MethodChannel.Result) {
        val ctx = appContext ?: activity ?: return
        val intent = Intent(ctx, AnotherVpnService::class.java).apply {
            action = AnotherVpnService.ACTION_START
            putExtra(AnotherVpnService.EXTRA_CLIENT_ID, call.argument<String>("clientId"))
            putExtra(AnotherVpnService.EXTRA_KEYSTORE, call.argument<String>("keyStoreDir"))
            putExtra(AnotherVpnService.EXTRA_NODES, call.argument<String>("nodesJson"))
            putExtra(AnotherVpnService.EXTRA_DEST_HOST, call.argument<String>("destHost") ?: "")
            putExtra(AnotherVpnService.EXTRA_DEST_PORT, call.argument<Int>("destPort") ?: 0)
        }
        ctx.startForegroundService(intent)
        result.success(mapOf("ok" to true))
    }

    private fun parseJson(raw: String): Map<String, Any?> {
        val obj = JSONObject(raw)
        val out = HashMap<String, Any?>()
        obj.keys().forEach { key -> out[key] = obj.opt(key) }
        return out
    }

    companion object {
        private const val REQ_VPN = 4721
    }
}
