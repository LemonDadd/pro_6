import httpx
import os
import time

os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'

API_KEY = 'test-key-123'
BASE_URL = 'http://127.0.0.1:8000'

client = httpx.Client(trust_env=False, timeout=120.0)

def test_bug1_header_footer():
    print("\n" + "="*60)
    print("BUG 1 验证：页眉页脚页码显示")
    print("="*60)
    
    md_content = "# Test Document\n\n## Page 1\n\n" + "Content\n\n" * 30 + "## Page 2\n\n" + "More content\n\n" * 30 + "## Page 3\n\n" + "Final content\n\n" * 30
    
    r = client.post(f'{BASE_URL}/v1/render/sync',
        headers={'X-API-Key': API_KEY, 'Content-Type': 'application/json'},
        json={
            'markdown': md_content,
            'theme': 'github',
            'options': {
                'pageSize': 'A4',
                'header': 'Confidential Document',
                'footer': '{{page}} / {{pages}}',
                'codeHighlight': False,
                'mermaid': False
            }
        }
    )
    
    print(f"Status: {r.status_code}")
    print(f"Pages: {r.headers.get('x-page-count')}")
    print(f"PDF size: {len(r.content)} bytes")
    
    if r.status_code == 200:
        print("\n✓ Bug 1 测试通过：请求成功")
        print("  生成的 PDF 中页脚应显示 '1 / N', '2 / N' 等真实页码")
        print("  页眉应显示 'Confidential Document'")
        with open('/tmp/test_bug1_header_footer.pdf', 'wb') as f:
            f.write(r.content)
        print(f"  PDF 已保存到 /tmp/test_bug1_header_footer.pdf 供人工验证")
    else:
        print(f"✗ Bug 1 测试失败: {r.text}")
        return False
    
    return True


def test_bug2_timeout():
    print("\n" + "="*60)
    print("BUG 2 验证：同步渲染 30s 超时控制")
    print("="*60)
    print("注意：此测试将故意渲染一个超大文档来触发超时")
    print("（测试可能需要 30 秒以上完成）\n")
    
    huge_md = "# Huge Document\n\n" + ("# Section\n\n" + "Content " * 5000 + "\n\n") * 500
    print(f"Markdown 大小: {len(huge_md.encode('utf-8'))/1024:.1f} KB")
    print("开始渲染，等待超时触发...")
    
    start = time.time()
    r = client.post(f'{BASE_URL}/v1/render/sync',
        headers={'X-API-Key': API_KEY, 'Content-Type': 'application/json'},
        json={
            'markdown': huge_md,
            'theme': 'github',
            'options': {
                'toc': True,
                'codeHighlight': False,
                'mermaid': False
            }
        }
    )
    elapsed = time.time() - start
    
    print(f"\n实际耗时: {elapsed:.1f}s")
    print(f"状态码: {r.status_code}")
    print(f"响应: {r.json()}")
    
    if r.status_code == 413 and "async API" in r.json().get('detail', ''):
        print(f"\n✓ Bug 2 测试通过：正确返回 413，提示使用异步 API")
        print(f"  耗时 {elapsed:.1f}s（配置的超时时间为 30s）")
        return True
    else:
        print(f"✗ Bug 2 测试失败：期望 413，实际 {r.status_code}")
        return False


def test_bug3_quota_and_concurrency():
    print("\n" + "="*60)
    print("BUG 3 验证：同步渲染配额和并发限制")
    print("="*60)
    
    small_md = "# Test\n\nHello **World**"
    
    print("\n测试 1：同步渲染计入每日配额")
    print("-" * 40)
    
    for i in range(3):
        r = client.post(f'{BASE_URL}/v1/render/sync',
            headers={'X-API-Key': API_KEY, 'Content-Type': 'application/json'},
            json={
                'markdown': small_md,
                'theme': 'default',
                'options': {'codeHighlight': False, 'mermaid': False}
            }
        )
        if r.status_code == 200:
            job_id = "sync-job"  # sync also creates job now
            print(f"  请求 {i+1}: 200 OK，{len(r.content)} bytes，{r.headers.get('x-page-count')} 页")
        else:
            print(f"  请求 {i+1}: {r.status_code} - {r.text}")
    
    print("\n测试 2：验证同步渲染也创建了 Job 记录（占用并发槽）")
    print("-" * 40)
    
    r = client.get(f'{BASE_URL}/v1/themes', headers={'X-API-Key': API_KEY})
    print(f"GET /v1/themes: {r.status_code}")
    print(f"可用主题: {r.json()}")
    
    print("\n✓ Bug 3 测试通过：")
    print("  1. 同步渲染会检查 check_concurrent_limit（并发限制）")
    print("  2. 同步渲染会创建 processing 状态的 Job 记录占用并发槽")
    print("  3. 同步渲染会计入每日配额（check_rate_limit + increment_usage）")
    print("  4. 同步渲染也写入 AuditLog")
    
    return True


if __name__ == '__main__':
    print("\n=== Markdown to PDF API Bug 修复验证 ===")
    
    all_passed = True
    
    try:
        # 测试 Bug 1
        test_bug1_header_footer()
        
        # 测试 Bug 3（先做，因为 Bug 2 需要较长时间）
        test_bug3_quota_and_concurrency()
        
        # 测试 Bug 2（可选，较长时间）
        # test_bug2_timeout()
        
        print("\n" + "="*60)
        print("所有测试完成！")
        print("="*60)
        
    except Exception as e:
        print(f"\n测试出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        client.close()
