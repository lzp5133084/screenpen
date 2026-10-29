package cn.ecojia.screenpen;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.os.IBinder;
import android.util.DisplayMetrics;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.TextView;

/**
 * 悬浮球服务：悬浮窗覆盖在所有应用之上，轻点悬浮球进入标注模式。
 */
public class FloatService extends Service {

    public static volatile boolean running = false;

    private static final String CHANNEL_ID = "screenpen_float";
    private static final int NOTIFY_ID = 1001;
    private static final int DIM = 0xFF9AA0AC;

    private static final int ACT_TOOL = 1;
    private static final int ACT_COLOR = 2;
    private static final int ACT_PASS = 3;
    private static final int ACT_UNDO = 4;
    private static final int ACT_CLEAR = 5;
    private static final int ACT_COLLAPSE = 6;
    private static final int ACT_QUIT = 7;

    private static final int[] COLORS = {
            0xFFE8C87A, 0xFFFF4D5E, 0xFFFF9F45, 0xFF3DDC97,
            0xFF38E1E8, 0xFF4C8DFF, 0xFFB57BFF, 0xFFFFFFFF
    };

    private WindowManager wm;
    private SharedPreferences prefs;

    private DrawView draw;
    private BallView ball;
    private LinearLayout bar;
    private WindowManager.LayoutParams ballLp;
    private WindowManager.LayoutParams drawLp;
    private WindowManager.LayoutParams barLp;

    private LinearLayout toolRow;
    private LinearLayout colorRow;
    private TextView passBtn;

    private boolean drawing;
    private boolean passthrough;
    private float dp;

    /** 悬浮球回调（避免使用匿名内部类，R8 对 javac 21 生成的匿名类存在兼容问题） */
    private static class BallListener implements BallView.Listener {
        private final FloatService svc;

        BallListener(FloatService s) {
            svc = s;
        }

        @Override
        public void onTap() {
            if (svc.drawing) {
                svc.exitDrawing();
            } else {
                svc.enterDrawing();
            }
        }

        @Override
        public void onDrag(int dx, int dy) {
            svc.moveBall(dx, dy);
        }
    }

    /** 工具条按钮点击 */
    private static class Click implements View.OnClickListener {
        private final FloatService svc;
        private final int action;

        Click(FloatService s, int a) {
            svc = s;
            action = a;
        }

        @Override
        public void onClick(View v) {
            switch (action) {
                case ACT_TOOL:
                    svc.selectTool((String) v.getTag());
                    break;
                case ACT_COLOR:
                    svc.selectColor((Integer) v.getTag());
                    break;
                case ACT_PASS:
                    svc.setPassthrough(!svc.passthrough);
                    break;
                case ACT_UNDO:
                    svc.draw.undo();
                    break;
                case ACT_CLEAR:
                    svc.draw.clear();
                    break;
                case ACT_COLLAPSE:
                    svc.exitDrawing();
                    break;
                case ACT_QUIT:
                    svc.stopSelf();
                    break;
            }
        }
    }

    @Override
    public void onCreate() {
        super.onCreate();
        if (!android.provider.Settings.canDrawOverlays(this)) {
            running = false;
            return;
        }
        running = true;
        dp = getResources().getDisplayMetrics().density;
        wm = (WindowManager) getSystemService(Context.WINDOW_SERVICE);
        prefs = getSharedPreferences("screenpen", MODE_PRIVATE);

        createNotificationChannel();
        buildBall();
        buildDrawLayer();
        buildBar();
        showBall();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        startForeground(NOTIFY_ID, buildNotification());
        if (!android.provider.Settings.canDrawOverlays(this)) {
            stopSelf();
            return START_NOT_STICKY;
        }
        return START_STICKY;
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public void onDestroy() {
        running = false;
        removeSafely(ball);
        removeSafely(bar);
        removeSafely(draw);
        super.onDestroy();
    }

    // ------------------------------------------------------------ 通知
    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel ch = new NotificationChannel(CHANNEL_ID, "鼠标画笔悬浮球",
                    NotificationManager.IMPORTANCE_LOW);
            ch.setShowBadge(false);
            NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
            nm.createNotificationChannel(ch);
        }
    }

    private Notification buildNotification() {
        Intent i = new Intent(this, MainActivity.class);
        int flags = Build.VERSION.SDK_INT >= 23
                ? PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
                : PendingIntent.FLAG_UPDATE_CURRENT;
        PendingIntent pi = PendingIntent.getActivity(this, 0, i, flags);

        Notification.Builder b = Build.VERSION.SDK_INT >= 26
                ? new Notification.Builder(this, CHANNEL_ID)
                : new Notification.Builder(this);
        return b.setContentTitle("鼠标画笔正在运行")
                .setContentText("点悬浮球即可在任意界面上标注")
                .setSmallIcon(android.R.drawable.ic_menu_edit)
                .setContentIntent(pi)
                .setOngoing(true)
                .build();
    }

    // ------------------------------------------------------------ 悬浮球
    private void buildBall() {
        ball = new BallView(this);
        int size = (int) (54 * dp);
        ballLp = new WindowManager.LayoutParams(size, size,
                overlayType(),
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                        | WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL
                        | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS
                        | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                PixelFormat.TRANSLUCENT);
        ballLp.gravity = Gravity.TOP | Gravity.START;

        DisplayMetrics dm = new DisplayMetrics();
        wm.getDefaultDisplay().getRealMetrics(dm);
        ballLp.x = dm.widthPixels - size - (int) (10 * dp);
        ballLp.y = (int) (dm.heightPixels * 0.32f);

        ball.setListener(new BallListener(this));
    }

    private void moveBall(int dx, int dy) {
        DisplayMetrics d = new DisplayMetrics();
        wm.getDefaultDisplay().getRealMetrics(d);
        ballLp.x = Math.max(-(int) (10 * dp),
                Math.min(ballLp.x + dx, d.widthPixels - ball.getWidth() + (int) (10 * dp)));
        ballLp.y = Math.max(0, Math.min(ballLp.y + dy, d.heightPixels - ball.getHeight()));
        if (ball.getParent() != null) {
            wm.updateViewLayout(ball, ballLp);
        }
    }

    private void showBall() {
        if (ball.getParent() == null) {
            wm.addView(ball, ballLp);
        }
    }

    // ------------------------------------------------------------ 标注层
    private void buildDrawLayer() {
        draw = new DrawView(this);
        draw.setTool(prefs.getString("tool", DrawView.PEN));
        draw.setColor(prefs.getInt("color", COLORS[0]));
        drawLp = new WindowManager.LayoutParams(
                WindowManager.LayoutParams.MATCH_PARENT,
                WindowManager.LayoutParams.MATCH_PARENT,
                overlayType(),
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                        | WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL
                        | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS
                        | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                PixelFormat.TRANSLUCENT);
        drawLp.gravity = Gravity.TOP | Gravity.START;
    }

    // ------------------------------------------------------------ 工具条
    private void buildBar() {
        bar = new LinearLayout(this);
        bar.setOrientation(LinearLayout.VERTICAL);
        int pad = (int) (8 * dp);
        bar.setPadding(pad, pad, pad, pad);
        bar.setBackground(round(0xF20A0B0F, 0x66E8C87A, 16 * dp));

        toolRow = new LinearLayout(this);
        toolRow.setOrientation(LinearLayout.HORIZONTAL);
        for (int i = 0; i < DrawView.TOOL_KEYS.length; i++) {
            TextView btn = chip(DrawView.TOOL_NAMES[i]);
            btn.setTag(DrawView.TOOL_KEYS[i]);
            btn.setOnClickListener(new Click(this, ACT_TOOL));
            toolRow.addView(btn);
        }

        colorRow = new LinearLayout(this);
        colorRow.setOrientation(LinearLayout.HORIZONTAL);
        for (int i = 0; i < COLORS.length; i++) {
            View dot = new View(this);
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                    (int) (26 * dp), (int) (26 * dp));
            lp.rightMargin = (int) (6 * dp);
            lp.topMargin = (int) (6 * dp);
            dot.setLayoutParams(lp);
            dot.setTag(COLORS[i]);
            dot.setOnClickListener(new Click(this, ACT_COLOR));
            colorRow.addView(dot);
        }

        passBtn = chip("穿透");
        passBtn.setOnClickListener(new Click(this, ACT_PASS));

        TextView undo = chip("撤销");
        undo.setOnClickListener(new Click(this, ACT_UNDO));

        TextView clear = chip("清空");
        clear.setOnClickListener(new Click(this, ACT_CLEAR));

        TextView collapse = chip("收起");
        collapse.setOnClickListener(new Click(this, ACT_COLLAPSE));

        TextView quit = chip("退出");
        quit.setOnClickListener(new Click(this, ACT_QUIT));

        LinearLayout actRow = new LinearLayout(this);
        actRow.setOrientation(LinearLayout.HORIZONTAL);
        actRow.addView(passBtn);
        actRow.addView(undo);
        actRow.addView(clear);
        actRow.addView(collapse);
        actRow.addView(quit);

        bar.addView(wrap(toolRow));
        bar.addView(wrap(colorRow));
        bar.addView(wrap(actRow));

        barLp = new WindowManager.LayoutParams(
                WindowManager.LayoutParams.MATCH_PARENT,
                WindowManager.LayoutParams.WRAP_CONTENT,
                overlayType(),
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                        | WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL
                        | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                PixelFormat.TRANSLUCENT);
        barLp.gravity = Gravity.TOP | Gravity.START;
        barLp.y = statusBarHeight() + (int) (4 * dp);
        barLp.x = (int) (6 * dp);

        refreshChips();
    }

    private void selectTool(String key) {
        draw.setTool(key);
        prefs.edit().putString("tool", key).apply();
        refreshChips();
    }

    private void selectColor(int c) {
        draw.setColor(c);
        prefs.edit().putInt("color", c).apply();
        refreshChips();
    }

    private HorizontalScrollView wrap(View content) {
        HorizontalScrollView hs = new HorizontalScrollView(this);
        hs.setHorizontalScrollBarEnabled(false);
        hs.addView(content);
        return hs;
    }

    private TextView chip(String text) {
        TextView tv = new TextView(this);
        tv.setText(text);
        tv.setTextSize(11);
        tv.setTextColor(DIM);
        tv.setGravity(Gravity.CENTER);
        tv.setPadding((int) (8 * dp), (int) (5 * dp), (int) (8 * dp), (int) (5 * dp));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        lp.rightMargin = (int) (6 * dp);
        lp.topMargin = (int) (4 * dp);
        tv.setLayoutParams(lp);
        return tv;
    }

    private void refreshChips() {
        for (int i = 0; i < toolRow.getChildCount(); i++) {
            View v = toolRow.getChildAt(i);
            boolean on = draw.getTool().equals(v.getTag());
            v.setBackground(round(on ? 0x33E8C87A : 0x00000000, on ? 0xB3E8C87A : 0x1AFFFFFF, 9 * dp));
            ((TextView) v).setTextColor(on ? 0xFFF7E8BE : DIM);
        }
        for (int i = 0; i < colorRow.getChildCount(); i++) {
            View v = colorRow.getChildAt(i);
            boolean on = ((Integer) v.getTag()) == draw.getColor();
            v.setBackground(round((Integer) v.getTag(), on ? 0xFFE8C87A : 0x33FFFFFF, 13 * dp));
        }
        if (passBtn != null) {
            passBtn.setText(passthrough ? "绘画" : "穿透");
            passBtn.setTextColor(passthrough ? 0xFFF7E8BE : DIM);
            passBtn.setBackground(round(passthrough ? 0x33E8C87A : 0x00000000,
                    passthrough ? 0xB3E8C87A : 0x1AFFFFFF, 9 * dp));
        }
    }

    private GradientDrawable round(int fill, int stroke, float radius) {
        GradientDrawable g = new GradientDrawable();
        g.setShape(GradientDrawable.RECTANGLE);
        g.setColor(fill);
        g.setCornerRadius(radius);
        if (Color.alpha(stroke) > 0) {
            g.setStroke((int) dp, stroke);
        }
        return g;
    }

    // ------------------------------------------------------------ 模式切换
    private void enterDrawing() {
        drawing = true;
        setPassthrough(false);
        if (ball.getParent() != null) {
            wm.removeView(ball);
        }
        if (draw.getParent() == null) {
            wm.addView(draw, drawLp);
        }
        if (bar.getParent() == null) {
            wm.addView(bar, barLp);
        }
        wm.addView(ball, ballLp);
        refreshChips();
    }

    private void exitDrawing() {
        drawing = false;
        removeSafely(bar);
        removeSafely(draw);
        showBall();
    }

    private void setPassthrough(boolean on) {
        passthrough = on;
        if (on) {
            drawLp.flags |= WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE;
        } else {
            drawLp.flags &= ~WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE;
        }
        if (draw.getParent() != null) {
            wm.updateViewLayout(draw, drawLp);
        }
        refreshChips();
    }

    private void removeSafely(View v) {
        if (v != null && v.getParent() != null) {
            try {
                wm.removeView(v);
            } catch (Exception ignored) {
            }
        }
    }

    private int overlayType() {
        if (Build.VERSION.SDK_INT >= 26) {
            return WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY;
        }
        return WindowManager.LayoutParams.TYPE_PHONE;
    }

    private int statusBarHeight() {
        int id = getResources().getIdentifier("status_bar_height", "dimen", "android");
        return id > 0 ? getResources().getDimensionPixelSize(id) : (int) (24 * dp);
    }
}
