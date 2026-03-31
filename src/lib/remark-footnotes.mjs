function text(value) {
  return { type: 'text', value };
}

function createLink(url, label, className, id, extraProperties = {}) {
  const classNameList = Array.isArray(className) ? className : [className];
  const properties = { className: classNameList, ...extraProperties };
  if (id) properties.id = id;

  return {
    type: 'link',
    url,
    data: {
      hProperties: properties
    },
    children: [text(label)]
  };
}

function cloneNode(node) {
  return JSON.parse(JSON.stringify(node));
}

function visit(node, callback, parent = null, index = -1) {
  callback(node, parent, index);
  if (!node || !Array.isArray(node.children)) return;
  node.children.forEach((child, childIndex) => visit(child, callback, node, childIndex));
}

export default function remarkFootnotes() {
  return function transformer(tree) {
    const definitions = new Map();

    tree.children = tree.children.filter((node) => {
      if (node.type === 'footnoteDefinition') {
        definitions.set(node.identifier, node);
        return false;
      }
      return true;
    });

    const order = [];
    const numbers = new Map();
    const referenceCounts = new Map();
    const backrefs = new Map();

    visit(tree, (node, parent, index) => {
      if (node.type !== 'footnoteReference' || !parent || index < 0) return;

      if (!numbers.has(node.identifier)) {
        numbers.set(node.identifier, order.length + 1);
        order.push(node.identifier);
      }

      const number = numbers.get(node.identifier);
      const count = (referenceCounts.get(node.identifier) ?? 0) + 1;
      referenceCounts.set(node.identifier, count);

      const refId = `fnref-${number}-${count}`;
      const refs = backrefs.get(node.identifier) ?? [];
      refs.push(refId);
      backrefs.set(node.identifier, refs);

      parent.children[index] = createLink(
        `#fn-${number}`,
        `[${number}]`,
        'footnote-ref',
        refId
      );
    });

    if (!order.length) return;

    tree.children.push({
      type: 'list',
      ordered: true,
      spread: false,
      data: {
        hProperties: {
          className: ['footnotes-list']
        }
      },
      children: order.map((identifier) => {
        const number = numbers.get(identifier);
        const definition = definitions.get(identifier);
        const children = (definition?.children ?? []).map(cloneNode);

        if (!children.length || children[0].type !== 'paragraph') {
          children.unshift({ type: 'paragraph', children: [] });
        }

        const prefix = [];
        const refs = backrefs.get(identifier) ?? [];

        refs.forEach((refId, refIndex) => {
          if (refIndex > 0) prefix.push(text(' '));
          prefix.push(
            createLink(
              `#${refId}`,
              `[${number}]`,
              'footnote-backref-label',
              null,
              { 'aria-label': `Back to reference ${number}${refs.length > 1 ? `.${refIndex + 1}` : ''}` }
            )
          );
        });

        if (prefix.length > 0) {
          prefix.push(text('\u00A0'));
          children[0].children = [...prefix, ...children[0].children];
        }

        return {
          type: 'listItem',
          spread: false,
          data: {
            hProperties: {
              id: `fn-${number}`
            }
          },
          children
        };
      })
    });
  };
}
