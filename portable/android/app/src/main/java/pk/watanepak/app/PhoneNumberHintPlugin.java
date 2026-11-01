package pk.watanepak.app;

import android.app.Activity;
import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.IntentSenderRequest;
import androidx.activity.result.contract.ActivityResultContracts;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.google.android.gms.auth.api.identity.GetPhoneNumberHintIntentRequest;
import com.google.android.gms.auth.api.identity.Identity;

@CapacitorPlugin(name = "PhoneNumberHint")
public class PhoneNumberHintPlugin extends Plugin {
    private ActivityResultLauncher<IntentSenderRequest> hintLauncher;
    private PluginCall pendingCall;

    @Override
    public void load() {
        hintLauncher = getBridge().registerForActivityResult(
            new ActivityResultContracts.StartIntentSenderForResult(), result -> {
                PluginCall call = pendingCall;
                pendingCall = null;
                if (call == null) return;
                if (result.getResultCode() != Activity.RESULT_OK || result.getData() == null) {
                    call.reject("Phone number selection cancelled.", "USER_CANCELLED");
                    return;
                }
                try {
                    String phoneNumber = Identity.getSignInClient(getContext()).getPhoneNumberFromIntent(result.getData());
                    JSObject value = new JSObject();
                    value.put("phoneNumber", phoneNumber);
                    call.resolve(value);
                } catch (Exception error) {
                    call.reject("Could not read the selected phone number.", error);
                }
            }
        );
    }

    @PluginMethod
    public void pick(PluginCall call) {
        if (pendingCall != null) {
            call.reject("A phone number picker is already open.");
            return;
        }
        pendingCall = call;
        GetPhoneNumberHintIntentRequest request = GetPhoneNumberHintIntentRequest.builder().build();
        Identity.getSignInClient(getContext()).getPhoneNumberHintIntent(request)
            .addOnSuccessListener(pendingIntent -> hintLauncher.launch(new IntentSenderRequest.Builder(pendingIntent.getIntentSender()).build()))
            .addOnFailureListener(error -> {
                pendingCall = null;
                call.reject("Phone number suggestions are unavailable on this device.", error);
            });
    }
}
