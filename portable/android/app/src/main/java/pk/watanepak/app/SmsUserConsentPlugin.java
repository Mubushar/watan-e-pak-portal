package pk.watanepak.app;

import android.app.Activity;
import android.content.BroadcastReceiver;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.os.Bundle;
import androidx.activity.result.ActivityResult;
import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.core.content.ContextCompat;
import androidx.core.os.BundleCompat;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.google.android.gms.auth.api.phone.SmsRetriever;
import com.google.android.gms.common.api.CommonStatusCodes;
import com.google.android.gms.common.api.Status;

/**
 * Reads the sign-in code SMS with the user's permission (Google's SMS User Consent API).
 *
 * The app holds no SMS permission. After {@code waitForCode()} Android watches for the next
 * SMS that contains a code (5 minutes) and asks "Allow Watan-e-Pak to read this message?".
 * Only a message the user allows reaches the app; declining or the timeout rejects the call.
 */
@CapacitorPlugin(name = "SmsUserConsent")
public class SmsUserConsentPlugin extends Plugin {
    private static final String PLAY_SERVICES = "com.google.android.gms";

    private ActivityResultLauncher<Intent> consentLauncher;
    private BroadcastReceiver receiver;
    private PluginCall pendingCall;

    @Override
    public void load() {
        consentLauncher = getBridge().registerForActivityResult(
            new ActivityResultContracts.StartActivityForResult(), this::onConsentResult
        );
    }

    @PluginMethod
    public void waitForCode(PluginCall call) {
        finish(null, "Replaced by a newer request.", "CANCELLED");
        pendingCall = call;
        receiver = new BroadcastReceiver() {
            @Override
            public void onReceive(Context context, Intent intent) {
                onSmsRetrieved(intent);
            }
        };
        ContextCompat.registerReceiver(
            getContext(), receiver, new IntentFilter(SmsRetriever.SMS_RETRIEVED_ACTION),
            SmsRetriever.SEND_PERMISSION, null, ContextCompat.RECEIVER_EXPORTED
        );
        // null sender: the code may come from any number that is not in the user's contacts.
        SmsRetriever.getClient(getContext()).startSmsUserConsent(null)
            .addOnFailureListener(error -> finish(null, "Reading the code SMS is unavailable on this device.", "UNAVAILABLE"));
    }

    @PluginMethod
    public void cancel(PluginCall call) {
        finish(null, "Cancelled.", "CANCELLED");
        call.resolve();
    }

    private void onSmsRetrieved(Intent intent) {
        if (!SmsRetriever.SMS_RETRIEVED_ACTION.equals(intent.getAction()) || intent.getExtras() == null) return;
        Bundle extras = intent.getExtras();
        Status status = BundleCompat.getParcelable(extras, SmsRetriever.EXTRA_STATUS, Status.class);
        int code = status != null ? status.getStatusCode() : CommonStatusCodes.ERROR;
        if (code == CommonStatusCodes.TIMEOUT) {
            finish(null, "No code SMS arrived in time.", "TIMEOUT");
            return;
        }
        Intent consent = code == CommonStatusCodes.SUCCESS
            ? BundleCompat.getParcelable(extras, SmsRetriever.EXTRA_CONSENT_INTENT, Intent.class)
            : null;
        // Only launch Google Play services' own consent screen, never an intent that grants URI
        // access (guards against intent redirection).
        ComponentName target = consent != null ? consent.getComponent() : null;
        int uriGrants = Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION;
        if (target == null || !PLAY_SERVICES.equals(target.getPackageName()) || (consent.getFlags() & uriGrants) != 0) {
            finish(null, "Could not read the code SMS.", "ERROR");
            return;
        }
        consentLauncher.launch(consent);
    }

    private void onConsentResult(ActivityResult result) {
        Intent data = result.getData();
        String message = data != null ? data.getStringExtra(SmsRetriever.EXTRA_SMS_MESSAGE) : null;
        if (result.getResultCode() == Activity.RESULT_OK && message != null) {
            JSObject value = new JSObject();
            value.put("message", message);
            finish(value, null, null);
        } else {
            finish(null, "You chose not to share the message.", "DENIED");
        }
    }

    /** Resolve (value) or reject (message, code) the waiting call and stop listening. */
    private void finish(JSObject value, String message, String code) {
        if (receiver != null) {
            try {
                getContext().unregisterReceiver(receiver);
            } catch (IllegalArgumentException ignored) {
                // already unregistered
            }
            receiver = null;
        }
        PluginCall call = pendingCall;
        pendingCall = null;
        if (call == null) return;
        if (value != null) call.resolve(value);
        else call.reject(message, code);
    }

    @Override
    protected void handleOnDestroy() {
        finish(null, "The app was closed.", "CANCELLED");
    }
}
