module.exports = {
	"env": {
		"browser": true,
		"node": true,
		"es6": true
	},
	"extends": "eslint:recommended",
	"parserOptions": {
		"ecmaVersion": 8,
		"sourceType": "module",
		"ecmaFeatures": {
			"impliedStrict": true
		}
	},
	"rules": {
		"quotes": ["error", "double"],
		"semi": ["error", "always"],
		"indent": ["error", "tab", { "ObjectExpression": "first" }]
	}
};