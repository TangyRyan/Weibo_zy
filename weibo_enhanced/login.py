def login(self):
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=self.config.playwright_headless)

    # 尝试加载之前保存的登录状态
    try:
        self.context = browser.new_context(storage_state="auth_state.json")
        print("已加载保存的登录状态。")
        self.page = self.context.new_page()
        self.page.goto("https://weibo.com")
        self.page.wait_for_selector("text=首页", timeout=15000)
        print("自动登录成功！")
        return
    except Exception:
        print("无法使用保存的状态自动登录，将采用手动登录。")
        # 如果加载状态失败，则创建一个新的 context
        self.context = browser.new_context()

    if self.config.cookie:
        print("正在使用 Cookie 进行登录...")
        self.context.add_cookies([{'name': 'SUB', 'value': self.config.cookie, 'domain': '.weibo.com', 'path': '/'}])
        self.page = self.context.new_page()
        self.page.goto("https://weibo.com")
        try:
            self.page.wait_for_selector("text=首页", timeout=15000)
            print("Cookie 登录成功！")
        except TimeoutError:
            print("Cookie 已失效或不正确，请删除 auth_state.json 后重试扫码登录。")
            exit()
    else:
        print("请在打开的浏览器窗口中扫描二维码登录...")
        self.page = self.context.new_page()
        login_url = "https://passport.weibo.com/sso/signin?entry=miniblog&source=miniblog&disp=popup&url=https%3A%2F%2Fweibo.com%2Fnewlogin%3Ftabtype%3Dweibo%26gid%3D102803%26openLoginLayer%3D0%26url%3Dhttps%253A%252F%252Fweibo.com%252F&from=weibopro"
        self.page.goto(login_url)
        print("等待用户登录...")
        try:
            self.page.wait_for_selector("text=首页", timeout=120000)  # 2分钟超时
            print("登录成功！")
        except TimeoutError:
            print("登录超时，请重试。")
            exit()

    # 保存登录状态以备下次使用
    storage = self.context.storage_state()
    self._save_json(storage, "auth_state.json")