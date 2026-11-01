package pk.watanepak.app;

import com.getcapacitor.BridgeActivity;
import android.os.Bundle;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(PhoneNumberHintPlugin.class);
        registerPlugin(SmsUserConsentPlugin.class);
        super.onCreate(savedInstanceState);
    }
}
