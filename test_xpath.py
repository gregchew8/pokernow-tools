from lxml import etree

html = """
<html>
<body>
  <div class="row">
    Use cents values?
    <button>YES</button> <button>NO</button>
  </div>
  <div class="row">
    <span>Allow Rebuy?</span>
    <button>YES</button> <button>NO</button>
  </div>
  <div class="row">
    <div>
        <div>Decision Time Limit</div>
    </div>
    <input id="decision" />
  </div>
</body>
</html>
"""
tree = etree.HTML(html)

def test_toggle(label, option):
    # Find text node, then following button
    xpath = f"//text()[contains(., '{label}')]/following::button[normalize-space()='{option}'][1]"
    node = tree.xpath(xpath)
    print(f"Toggle '{label}' -> '{option}':", node[0].tag, node[0].text if node else "None")

def test_input(label):
    xpath = f"//text()[contains(., '{label}')]/following::input[1]"
    node = tree.xpath(xpath)
    print(f"Input '{label}':", node[0].tag, node[0].attrib if node else "None")

test_toggle('Use cents', 'YES')
test_toggle('Allow Rebuy', 'YES')
test_input('Decision Time')

